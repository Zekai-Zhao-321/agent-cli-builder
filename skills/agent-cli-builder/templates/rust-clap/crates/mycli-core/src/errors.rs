//! Exit-code taxonomy and the structured error envelope.
//!
//! The taxonomy is the same one documented in the parent skill's
//! `references/output_contract.md`. Do not invent new codes — agents and
//! humans have learned these conventions:
//!
//! | Code | Meaning                          | Recovery                           |
//! |------|----------------------------------|------------------------------------|
//! | 0    | Success                          | -                                  |
//! | 1    | General / internal error         | Retry once; surface if persistent  |
//! | 2    | Validation / usage error         | Fix arguments and retry            |
//! | 3    | Authentication / authorization   | Re-auth and retry                  |
//! | 4    | Quota / rate limit               | Backoff and retry                  |
//! | 5    | Timeout                          | Increase --timeout or use --async  |
//! | 6    | Network / transport              | Retry with backoff                 |
//! | 10   | Safety / policy block            | Do not retry; surface block reason |
//! | 130  | Interrupted (SIGINT)             | -                                  |
//!
//! `CliError` is the only error type the rest of the workspace propagates.
//! Library code constructs typed errors (`CliError::auth_expired(...)`); the
//! binary's top-level error wrap maps the variant -> `error.code`,
//! `error.exit_code`, and the human message before printing the envelope.

use thiserror::Error;

/// Stable string codes shipped in `error.code`. Add variants as new failure
/// classes appear; **never repurpose an existing variant** (agents may have
/// learned to branch on it).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCode {
    Internal,
    Validation,
    AuthMissing,
    AuthExpired,
    Forbidden,
    Quota,
    Timeout,
    Network,
    PolicyBlock,
    Interrupted,
}

impl ErrorCode {
    /// The numeric exit code an agent will branch on in `$?`.
    #[must_use]
    pub const fn exit_code(self) -> i32 {
        match self {
            Self::Internal => 1,
            Self::Validation => 2,
            Self::AuthMissing | Self::AuthExpired | Self::Forbidden => 3,
            Self::Quota => 4,
            Self::Timeout => 5,
            Self::Network => 6,
            Self::PolicyBlock => 10,
            Self::Interrupted => 130,
        }
    }

    /// The stable string code shipped in `error.code`. Snake-case; uppercase
    /// because agents pattern-match on these uppercase tokens.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Internal => "INTERNAL_ERROR",
            Self::Validation => "VALIDATION_ERROR",
            Self::AuthMissing => "AUTH_MISSING",
            Self::AuthExpired => "AUTH_EXPIRED",
            Self::Forbidden => "FORBIDDEN",
            Self::Quota => "QUOTA_EXCEEDED",
            Self::Timeout => "TIMEOUT",
            Self::Network => "NETWORK_ERROR",
            Self::PolicyBlock => "POLICY_BLOCK",
            Self::Interrupted => "INTERRUPTED",
        }
    }
}

/// The library's only error type. One variant per failure class; the
/// `suggestions` field is the recovery list shown in the error envelope
/// (`error.suggestions`), most-likely-fix first.
#[derive(Debug, Error)]
#[error("{message}")]
pub struct CliError {
    pub code: ErrorCode,
    pub message: String,
    pub suggestions: Vec<String>,
    /// Optional inner cause; if present, attached to `metadata.cause` in
    /// `--verbose` mode only (don't leak stacks to agents by default).
    #[source]
    pub source: Option<Box<dyn std::error::Error + Send + Sync + 'static>>,
}

impl CliError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            suggestions: Vec::new(),
            source: None,
        }
    }

    #[must_use]
    pub fn with_suggestions(mut self, suggestions: impl IntoIterator<Item = impl Into<String>>) -> Self {
        self.suggestions = suggestions.into_iter().map(Into::into).collect();
        self
    }

    #[must_use]
    pub fn with_source<E>(mut self, source: E) -> Self
    where
        E: std::error::Error + Send + Sync + 'static,
    {
        self.source = Some(Box::new(source));
        self
    }

    pub fn validation(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Validation, message)
    }

    pub fn auth_missing(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::AuthMissing, message)
    }

    pub fn auth_expired(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::AuthExpired, message)
    }

    pub fn quota(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Quota, message)
    }

    pub fn timeout(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Timeout, message)
    }

    pub fn network(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Network, message)
    }

    pub fn policy_block(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::PolicyBlock, message)
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Internal, message)
    }

    #[must_use]
    pub const fn exit_code(&self) -> i32 {
        self.code.exit_code()
    }
}

impl From<std::io::Error> for CliError {
    fn from(err: std::io::Error) -> Self {
        Self::internal(format!("I/O error: {err}")).with_source(err)
    }
}

impl From<serde_json::Error> for CliError {
    fn from(err: serde_json::Error) -> Self {
        Self::validation(format!("JSON parse error: {err}")).with_source(err)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_codes_match_taxonomy() {
        assert_eq!(ErrorCode::Validation.exit_code(), 2);
        assert_eq!(ErrorCode::AuthExpired.exit_code(), 3);
        assert_eq!(ErrorCode::Quota.exit_code(), 4);
        assert_eq!(ErrorCode::Timeout.exit_code(), 5);
        assert_eq!(ErrorCode::Network.exit_code(), 6);
        assert_eq!(ErrorCode::PolicyBlock.exit_code(), 10);
        assert_eq!(ErrorCode::Interrupted.exit_code(), 130);
    }

    #[test]
    fn error_code_strings_are_uppercase_stable() {
        // Agents pattern-match on these. Renaming any of them is a breaking
        // change; this test exists to make that explicit.
        assert_eq!(ErrorCode::Validation.as_str(), "VALIDATION_ERROR");
        assert_eq!(ErrorCode::AuthExpired.as_str(), "AUTH_EXPIRED");
    }
}
