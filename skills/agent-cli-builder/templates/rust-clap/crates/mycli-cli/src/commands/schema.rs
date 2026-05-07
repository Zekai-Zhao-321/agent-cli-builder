//! `mycli schema show <method>` — request + response JSON Schema for a method.
//! `mycli schema output <method>` — the literal stdout envelope shape.
//!
//! Both pull from `mycli_core::schemas::registered_methods()` so they cannot
//! drift from the actual wire format.

use serde_json::Value;
use strsim::normalized_levenshtein;

use mycli_core::errors::CliError;
use mycli_core::output::{Metadata, emit_success};
use mycli_core::schemas::{envelope_schema_for, registered_methods};

use crate::cli::{GlobalArgs, SchemaSub};

pub async fn run(sub: &SchemaSub, global: &GlobalArgs) -> Result<(), CliError> {
    match sub {
        SchemaSub::Show { method } => show(method, global),
        SchemaSub::Output { method } => output(method, global),
    }
}

fn show(method: &str, global: &GlobalArgs) -> Result<(), CliError> {
    let methods = registered_methods();
    let entry = methods.get(method).ok_or_else(|| unknown_method(method, &methods))?;
    let body = serde_json::json!({
        "method": method,
        "request": entry.request,
        "response": entry.response,
    });
    emit_success(global.resolved_format(), body, Metadata::new())
}

fn output(method: &str, global: &GlobalArgs) -> Result<(), CliError> {
    let methods = registered_methods();
    if !methods.contains_key(method) {
        return Err(unknown_method(method, &methods));
    }
    let schema = envelope_schema_for(method)
        .ok_or_else(|| CliError::internal(format!("envelope schema for '{method}' is missing")))?;
    emit_success(global.resolved_format(), schema, Metadata::new())
}

fn unknown_method<V>(method: &str, methods: &std::collections::BTreeMap<&'static str, V>) -> CliError {
    let mut suggestions: Vec<(&str, f64)> = methods
        .keys()
        .map(|k| (*k, normalized_levenshtein(method, k)))
        .collect();
    suggestions.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let close: Vec<String> = suggestions
        .iter()
        .filter(|(_, score)| *score > 0.5)
        .take(3)
        .map(|(name, _)| (*name).to_string())
        .collect();
    let mut msg = format!("no such method: {method}");
    if !close.is_empty() {
        msg.push_str(&format!(". Did you mean: {}?", close.join(", ")));
    }
    CliError::validation(msg).with_suggestions(
        suggestions
            .into_iter()
            .take(3)
            .map(|(name, _)| format!("mycli schema show {name}")),
    )
}

#[allow(dead_code)] // referenced from mod root only when crate is exercised
fn _value_assertion() -> Value {
    Value::Null
}
