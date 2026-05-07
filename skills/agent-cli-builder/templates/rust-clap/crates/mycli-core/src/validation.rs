//! Input hardening — invariant #9.
//!
//! Agents are *confidently wrong*. They invent paths, encode special
//! characters twice, paste in trailing newlines, and pass IDs that contain
//! query strings. Reject the surface those bugs hit; do it once, here, so
//! every command benefits.
//!
//! The rules:
//!
//! * Resource IDs may contain only printable ASCII letters, digits, dashes,
//!   underscores, dots, and colons. No `?#%/\..`, no whitespace, no control
//!   chars, no double-encoded sequences.
//! * Output paths are sandboxed to the current working directory. Reject
//!   absolute paths and any path that resolves outside CWD after canonical
//!   join.

use std::path::{Path, PathBuf};

use crate::errors::CliError;

const FORBIDDEN_ID_CHARS: &[char] = &['?', '#', '%', '/', '\\', ' ', '\t', '\n', '\r'];

/// Validate a resource ID (file id, task id, anything user-supplied).
pub fn validate_resource_id(id: &str) -> Result<(), CliError> {
    if id.is_empty() {
        return Err(CliError::validation("resource ID cannot be empty"));
    }
    if id.len() > 256 {
        return Err(CliError::validation(format!(
            "resource ID is {} chars; max 256",
            id.len()
        )));
    }
    if id.contains("..") {
        return Err(CliError::validation(format!(
            "resource ID '{id}' contains '..' (path traversal attempt)"
        )));
    }
    for c in id.chars() {
        if FORBIDDEN_ID_CHARS.contains(&c) {
            return Err(CliError::validation(format!(
                "resource ID '{id}' contains forbidden character {c:?}"
            ))
            .with_suggestions(["Pass clean IDs only — never embed query strings or paths."]));
        }
        if (c as u32) < 0x20 || (c as u32) == 0x7F {
            return Err(CliError::validation(format!(
                "resource ID '{id}' contains a control character"
            )));
        }
    }
    if id.contains('%') || id.contains("&amp;") {
        return Err(CliError::validation(format!(
            "resource ID '{id}' looks pre-encoded; pass the raw value and let the CLI percent-encode"
        )));
    }
    Ok(())
}

/// Sandbox an output path to CWD. Any path that resolves outside the working
/// directory after `canonicalize` is rejected. Existing parent dirs only —
/// the file itself need not exist yet.
pub fn validate_output_path(path: &Path) -> Result<PathBuf, CliError> {
    if path.as_os_str().is_empty() {
        return Err(CliError::validation("output path cannot be empty"));
    }
    if path.is_absolute() {
        return Err(CliError::validation(format!(
            "output path '{}' is absolute; must be relative to CWD",
            path.display()
        ))
        .with_suggestions([
            "Pass a path relative to the current working directory.",
            "Or `cd` to the directory you want the output in, then re-run.",
        ]));
    }
    let cwd = std::env::current_dir()
        .map_err(|e| CliError::internal(format!("cannot resolve CWD: {e}")))?;
    let joined = cwd.join(path);
    let parent = joined
        .parent()
        .ok_or_else(|| CliError::validation(format!("output path '{}' has no parent", path.display())))?;
    let canonical_parent = parent
        .canonicalize()
        .map_err(|e| CliError::validation(format!("output path parent does not exist: {e}")))?;
    let canonical_cwd = cwd
        .canonicalize()
        .map_err(|e| CliError::internal(format!("cannot canonicalize CWD: {e}")))?;
    if !canonical_parent.starts_with(&canonical_cwd) {
        return Err(CliError::validation(format!(
            "output path '{}' resolves outside CWD",
            path.display()
        )));
    }
    Ok(joined)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_empty_id() {
        assert!(validate_resource_id("").is_err());
    }

    #[test]
    fn rejects_path_traversal_in_id() {
        let err = validate_resource_id("../etc/passwd").unwrap_err();
        assert!(err.message.contains(".."));
    }

    #[test]
    fn rejects_query_chars_in_id() {
        for c in ['?', '#', '%', '/', '\\', ' '] {
            let id = format!("foo{c}bar");
            assert!(validate_resource_id(&id).is_err(), "should reject {c:?}");
        }
    }

    #[test]
    fn rejects_control_chars_in_id() {
        assert!(validate_resource_id("foo\u{0001}bar").is_err());
        assert!(validate_resource_id("foo\u{007F}bar").is_err());
    }

    #[test]
    fn accepts_clean_id() {
        assert!(validate_resource_id("task_abc-123.v2").is_ok());
        assert!(validate_resource_id("ns:resource_id").is_ok());
    }
}
