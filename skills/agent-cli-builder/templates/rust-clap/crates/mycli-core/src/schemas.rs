//! I/O types for every command.
//!
//! Each command's request and response live here as `serde + schemars`
//! types. `mycli schema show <method>` walks the registry below and emits
//! the JSON Schema; `mycli schema output <method>` emits the envelope shape
//! using the same types. The single source of truth is the Rust type — no
//! hand-maintained schema files to drift.
//!
//! Add new commands by:
//!
//! 1. Defining the request + response structs with derive(Serialize,
//!    Deserialize, JsonSchema).
//! 2. Adding an entry to `registered_methods()`.
//! 3. Wiring the command in `mycli-cli`.

use std::collections::BTreeMap;

use schemars::JsonSchema;
use schemars::schema::RootSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Request payload for `mycli hello`. Demo command — replace with yours.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct HelloRequest {
    /// Name to greet.
    pub name: String,
    /// Uppercase the greeting.
    #[serde(default)]
    pub shout: bool,
}

/// Response payload for `mycli hello`. Goes inside `data` of the envelope.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct HelloResponse {
    pub greeting: String,
    /// Set when `--dry-run` was passed; the CLI did not perform any side
    /// effect.
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub dry_run: bool,
}

/// One entry in the schema registry: the schemas for a single method.
pub struct MethodSchemas {
    pub request: RootSchema,
    pub response: RootSchema,
}

/// Generate the registry of every command's request/response schemas.
/// Looked up by `mycli schema show <method>`.
pub fn registered_methods() -> BTreeMap<&'static str, MethodSchemas> {
    let mut m: BTreeMap<&'static str, MethodSchemas> = BTreeMap::new();
    m.insert(
        "hello",
        MethodSchemas {
            request: schemars::schema_for!(HelloRequest),
            response: schemars::schema_for!(HelloResponse),
        },
    );
    m
}

/// Emit the envelope schema for a method — the literal `{ok, data, metadata}`
/// shape `mycli schema output <method>` returns. Same source-of-truth as
/// the actual envelope rendering: the data type comes from the same
/// `MethodSchemas` entry, so the schema cannot drift from the wire format.
pub fn envelope_schema_for(method: &str) -> Option<Value> {
    let schemas = registered_methods();
    let entry = schemas.get(method)?;
    let data_schema = serde_json::to_value(&entry.response).ok()?;
    Some(serde_json::json!({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": format!("{method} envelope"),
        "type": "object",
        "required": ["ok", "data", "metadata"],
        "properties": {
            "ok": { "type": "boolean", "const": true },
            "data": data_schema,
            "metadata": {
                "type": "object",
                "required": ["source"],
                "properties": {
                    "source": { "type": "string" },
                    "response_time_ms": { "type": "integer", "minimum": 0 }
                }
            }
        }
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hello_is_registered() {
        let m = registered_methods();
        assert!(m.contains_key("hello"));
    }

    #[test]
    fn envelope_schema_has_required_keys() {
        let v = envelope_schema_for("hello").unwrap();
        let required = v.get("required").unwrap().as_array().unwrap();
        let names: Vec<&str> = required.iter().filter_map(|x| x.as_str()).collect();
        assert!(names.contains(&"ok"));
        assert!(names.contains(&"data"));
        assert!(names.contains(&"metadata"));
    }
}
