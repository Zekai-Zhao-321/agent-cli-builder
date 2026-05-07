//! The output envelope and the rules for getting it onto the right stream.
//!
//! Two invariants from the parent skill anchor this module:
//!
//! * **#1 stream separation** — payloads go to stdout, everything else (logs,
//!   progress, hints, errors) to stderr. This module's `emit_*` functions
//!   only ever write to stdout.
//! * **#2 auto-JSON in non-TTY** — when stdout is being piped, the format
//!   defaults to JSON regardless of TTY-mode CLI flags. `OutputFormat::auto`
//!   does the detection; `OutputFormat::resolved()` collapses an explicit
//!   override into a final choice.
//!
//! And invariant #3 (the envelope shape) is encoded in [`Envelope`].

use std::fmt::Write as _;
use std::io::{self, IsTerminal as _, Write};

use serde::Serialize;
use serde_json::{Map, Value};

use crate::errors::CliError;

/// The success envelope shape. Generic over the `data` payload so each
/// command can use its own serde-derived type.
#[derive(Debug, Clone, Serialize)]
pub struct Envelope<T> {
    pub ok: bool,
    pub data: T,
    pub metadata: Metadata,
}

#[derive(Debug, Clone, Serialize)]
pub struct Metadata {
    pub source: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub response_time_ms: Option<u64>,
    /// Anything else the agent might want *about* the call rather than *from*
    /// the result (correlation IDs, deprecation warnings, page numbers, ...).
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

impl Metadata {
    pub fn new() -> Self {
        Self {
            source: crate::source_tag(),
            response_time_ms: None,
            extras: Map::new(),
        }
    }

    #[must_use]
    pub fn with_response_time(mut self, ms: u64) -> Self {
        self.response_time_ms = Some(ms);
        self
    }

    #[must_use]
    pub fn with_extra(mut self, key: impl Into<String>, value: impl Into<Value>) -> Self {
        self.extras.insert(key.into(), value.into());
        self
    }
}

impl Default for Metadata {
    fn default() -> Self {
        Self::new()
    }
}

/// User-facing output mode. `auto` defers to the TTY check at emission time.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputFormat {
    Auto,
    Json,
    Text,
}

impl OutputFormat {
    /// Resolve `Auto` to a concrete format: JSON when stdout is a pipe,
    /// Text when stdout is a real terminal.
    #[must_use]
    pub fn resolved(self) -> Self {
        match self {
            Self::Auto => {
                if io::stdout().is_terminal() {
                    Self::Text
                } else {
                    Self::Json
                }
            }
            other => other,
        }
    }

    /// Parse from a CLI flag value; case-insensitive.
    #[must_use]
    pub fn from_flag(s: &str) -> Option<Self> {
        match s.to_ascii_lowercase().as_str() {
            "auto" => Some(Self::Auto),
            "json" => Some(Self::Json),
            "text" => Some(Self::Text),
            _ => None,
        }
    }
}

/// Emit a success envelope to stdout. Always sanitizes control characters
/// before serialization so downstream `jq`-style parsers don't choke.
pub fn emit_success<T: Serialize>(format: OutputFormat, data: T, metadata: Metadata) -> Result<(), CliError> {
    let envelope = Envelope { ok: true, data, metadata };
    let value = serde_json::to_value(&envelope)?;
    let sanitized = sanitize(value);

    match format.resolved() {
        OutputFormat::Json | OutputFormat::Auto => write_stdout_line(&serde_json::to_string(&sanitized)?),
        OutputFormat::Text => write_stdout_line(&render_text(&sanitized)),
    }
}

/// Emit one NDJSON line per item — the right shape for any list endpoint.
/// Use `head -n N` upstream to cap consumption.
pub fn emit_ndjson<I, T>(items: I, mut metadata: Metadata) -> Result<(), CliError>
where
    I: IntoIterator<Item = T>,
    T: Serialize,
{
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    for (idx, item) in items.into_iter().enumerate() {
        let envelope = Envelope {
            ok: true,
            data: item,
            metadata: Metadata {
                source: metadata.source.clone(),
                response_time_ms: metadata.response_time_ms,
                extras: {
                    let mut m = metadata.extras.clone();
                    m.insert("index".into(), Value::from(idx));
                    m
                },
            },
        };
        let value = serde_json::to_value(&envelope)?;
        let sanitized = sanitize(value);
        writeln!(handle, "{}", serde_json::to_string(&sanitized)?)
            .map_err(|e| CliError::internal(format!("write failed: {e}")))?;
    }
    // Mark `metadata` consumed for the linter; we cloned what we needed above.
    metadata.extras.insert("ndjson".into(), Value::Bool(true));
    Ok(())
}

/// Emit an error envelope to stderr. The binary's top-level handler calls
/// this once per failed run and then `process::exit(err.exit_code())`.
pub fn emit_error(format: OutputFormat, err: &CliError) {
    let body = serde_json::json!({
        "ok": false,
        "error": {
            "code": err.code.as_str(),
            "exit_code": err.exit_code(),
            "message": err.message,
            "suggestions": err.suggestions,
        },
        "metadata": {
            "source": crate::source_tag(),
        }
    });
    let sanitized = sanitize(body);

    let stderr = io::stderr();
    let mut handle = stderr.lock();
    let _ = match format.resolved() {
        OutputFormat::Json | OutputFormat::Auto => writeln!(handle, "{}", serde_json::to_string(&sanitized).unwrap_or_default()),
        OutputFormat::Text => writeln!(handle, "{}", render_text_error(err)),
    };
}

fn write_stdout_line(line: &str) -> Result<(), CliError> {
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    writeln!(handle, "{line}").map_err(|e| CliError::internal(format!("write failed: {e}")))
}

fn render_text(value: &Value) -> String {
    // Minimal "pretty for humans" rendering. Real CLIs grow this into per-
    // command formatters; the contract for agents lives in the JSON path,
    // so this is allowed to be informal.
    if let Some(data) = value.get("data") {
        if let Some(s) = data.as_str() {
            return s.to_string();
        }
        match serde_json::to_string_pretty(data) {
            Ok(s) => s,
            Err(_) => data.to_string(),
        }
    } else {
        value.to_string()
    }
}

fn render_text_error(err: &CliError) -> String {
    let mut out = format!("error[{}]: {}", err.code.as_str(), err.message);
    if !err.suggestions.is_empty() {
        out.push_str("\nsuggestions:");
        for s in &err.suggestions {
            let _ = write!(out, "\n  - {s}");
        }
    }
    out
}

/// Recursively strip control characters from any string in the JSON tree.
/// Preserves \n (0x0A), \r (0x0D), \t (0x09); drops 0x00-0x08, 0x0B, 0x0C,
/// 0x0E-0x1F, and 0x7F (DEL). Apply at the envelope layer so every command
/// benefits without per-command thought.
pub fn sanitize(value: Value) -> Value {
    match value {
        Value::String(s) => Value::String(strip_control_chars(&s)),
        Value::Array(arr) => Value::Array(arr.into_iter().map(sanitize).collect()),
        Value::Object(map) => {
            Value::Object(map.into_iter().map(|(k, v)| (k, sanitize(v))).collect())
        }
        other => other,
    }
}

fn strip_control_chars(s: &str) -> String {
    s.chars()
        .filter(|&c| {
            let cu = c as u32;
            !(cu < 0x20 && c != '\n' && c != '\r' && c != '\t') && cu != 0x7F
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_control_chars_but_keeps_newlines_and_tabs() {
        let s = "hello\u{0007}world\n\ttabbed\u{007F}end";
        assert_eq!(strip_control_chars(s), "helloworld\n\ttabbedend");
    }

    #[test]
    fn sanitize_walks_arrays_and_objects() {
        let v = serde_json::json!({
            "msg": "a\u{0001}b",
            "list": ["c\u{0002}d", { "nested": "e\u{007F}f" }]
        });
        let cleaned = sanitize(v);
        assert_eq!(cleaned["msg"], "ab");
        assert_eq!(cleaned["list"][0], "cd");
        assert_eq!(cleaned["list"][1]["nested"], "ef");
    }

    #[test]
    fn output_format_parses_case_insensitively() {
        assert_eq!(OutputFormat::from_flag("JSON"), Some(OutputFormat::Json));
        assert_eq!(OutputFormat::from_flag("text"), Some(OutputFormat::Text));
        assert_eq!(OutputFormat::from_flag("Auto"), Some(OutputFormat::Auto));
        assert_eq!(OutputFormat::from_flag("yaml"), None);
    }
}
