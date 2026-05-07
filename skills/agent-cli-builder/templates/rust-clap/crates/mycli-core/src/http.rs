//! HTTP client wrapper that maps HTTP status codes onto our exit-code
//! taxonomy. Use this for every outbound API call rather than raw `reqwest`,
//! so 401/403/429/5xx fail with the correct semantic exit code without
//! per-call thought.
//!
//! Why `rustls-tls-native-roots`:
//!
//! * `rustls` instead of OpenSSL: zero system-OpenSSL dependency, single
//!   binary distributable, no compile-time link soup.
//! * `native-roots` instead of `webpki-roots`: picks up the OS trust store,
//!   which is what corporate-proxy CA chains end up in. Users behind a
//!   system-CA proxy (the kind whose IT injects a custom root cert into the
//!   system trust store) get TLS verification working out of the box.

use std::time::Duration;

use reqwest::StatusCode;
use serde::Serialize;
use serde::de::DeserializeOwned;

use crate::errors::CliError;

/// Thin wrapper around `reqwest::Client`. Construct once per process and
/// share via `Arc<HttpClient>` if multiple commands need it.
#[derive(Debug, Clone)]
pub struct HttpClient {
    inner: reqwest::Client,
    base_url: Option<String>,
}

impl HttpClient {
    pub fn new() -> Result<Self, CliError> {
        let inner = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent(format!("{}/{}", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| CliError::internal(format!("HTTP client build failed: {e}")))?;
        Ok(Self { inner, base_url: None })
    }

    #[must_use]
    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = Some(base_url.into());
        self
    }

    #[must_use]
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.inner = reqwest::Client::builder()
            .timeout(timeout)
            .user_agent(format!("{}/{}", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")))
            .build()
            .unwrap_or(self.inner);
        self
    }

    /// GET `<base>/<path>`. Returns deserialized JSON body, or maps the
    /// status code onto a `CliError` with the right exit code.
    pub async fn get<T: DeserializeOwned>(&self, path: &str, token: Option<&str>) -> Result<T, CliError> {
        let url = self.url_for(path);
        let mut req = self.inner.get(&url);
        if let Some(t) = token {
            req = req.bearer_auth(t);
        }
        let resp = req.send().await.map_err(map_send_error)?;
        decode_response(resp).await
    }

    /// POST a JSON body. Same status-code handling as `get`.
    pub async fn post<B: Serialize, T: DeserializeOwned>(
        &self,
        path: &str,
        body: &B,
        token: Option<&str>,
    ) -> Result<T, CliError> {
        let url = self.url_for(path);
        let mut req = self.inner.post(&url).json(body);
        if let Some(t) = token {
            req = req.bearer_auth(t);
        }
        let resp = req.send().await.map_err(map_send_error)?;
        decode_response(resp).await
    }

    fn url_for(&self, path: &str) -> String {
        match (&self.base_url, path.starts_with("http")) {
            (Some(base), false) => format!("{}/{}", base.trim_end_matches('/'), path.trim_start_matches('/')),
            _ => path.to_string(),
        }
    }
}

/// Map a `reqwest::Error` (sendside) onto our error taxonomy. Distinct from
/// status-code mapping because send errors fire before any HTTP exchange.
fn map_send_error(err: reqwest::Error) -> CliError {
    if err.is_timeout() {
        CliError::timeout(format!("HTTP request timed out: {err}"))
            .with_suggestions(["Increase --timeout, or split the work with --async."])
            .with_source(err)
    } else if err.is_connect() {
        CliError::network(format!("HTTP connection failed: {err}"))
            .with_suggestions([
                "Check network connectivity.",
                "Verify the service URL.",
                "If you're behind a corporate proxy, ensure HTTPS_PROXY is set.",
            ])
            .with_source(err)
    } else {
        CliError::network(format!("HTTP transport error: {err}")).with_source(err)
    }
}

async fn decode_response<T: DeserializeOwned>(resp: reqwest::Response) -> Result<T, CliError> {
    let status = resp.status();
    if status.is_success() {
        return resp
            .json::<T>()
            .await
            .map_err(|e| CliError::internal(format!("JSON decode failed: {e}")).with_source(e));
    }

    // Try to extract the server's error body for the message.
    let body = resp.text().await.unwrap_or_default();
    let snippet = body.chars().take(280).collect::<String>();

    let err = match status {
        StatusCode::UNAUTHORIZED => CliError::auth_expired(format!(
            "HTTP 401 from upstream: {snippet}"
        ))
        .with_suggestions([
            "Re-authenticate and retry.",
            "Confirm your token has not expired.",
        ]),
        StatusCode::FORBIDDEN => CliError::new(crate::errors::ErrorCode::Forbidden, format!(
            "HTTP 403 from upstream: {snippet}"
        ))
        .with_suggestions([
            "Confirm your token has the required scopes.",
            "If this is a different user's resource, request access first.",
        ]),
        StatusCode::TOO_MANY_REQUESTS => CliError::quota(format!(
            "HTTP 429 from upstream: {snippet}"
        ))
        .with_suggestions([
            "Backoff and retry — respect Retry-After if present.",
            "Reduce request rate or batch the work.",
        ]),
        StatusCode::REQUEST_TIMEOUT | StatusCode::GATEWAY_TIMEOUT => CliError::timeout(format!(
            "HTTP {status} from upstream: {snippet}"
        )),
        s if s.is_server_error() => CliError::network(format!(
            "HTTP {status} from upstream: {snippet}"
        ))
        .with_suggestions(["Retry with backoff; if persistent, the upstream service is down."]),
        s if s.is_client_error() => CliError::validation(format!(
            "HTTP {status} from upstream: {snippet}"
        ))
        .with_suggestions(["Check request shape via `mycli schema show <method>` and retry."]),
        _ => CliError::internal(format!("Unexpected HTTP status {status}: {snippet}")),
    };
    Err(err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn url_for_joins_base_and_path() {
        let c = HttpClient::new().unwrap().with_base_url("https://api.example.com/v1/");
        assert_eq!(c.url_for("/widgets"), "https://api.example.com/v1/widgets");
        assert_eq!(c.url_for("widgets"), "https://api.example.com/v1/widgets");
    }

    #[test]
    fn absolute_url_overrides_base() {
        let c = HttpClient::new().unwrap().with_base_url("https://api.example.com");
        assert_eq!(
            c.url_for("https://other.example.com/path"),
            "https://other.example.com/path"
        );
    }
}
