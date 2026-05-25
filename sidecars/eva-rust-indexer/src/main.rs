use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const BLOCKED_DIRS: &[&str] = &[
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    "target",
];

const READABLE_EXTENSIONS: &[&str] = &[
    "bat", "c", "cfg", "conf", "cpp", "cs", "css", "csv", "go", "h", "html", "ini",
    "java", "js", "json", "jsx", "log", "md", "mdx", "php", "ps1", "py", "rb", "rs",
    "sql", "toml", "ts", "tsx", "txt", "xml", "yaml", "yml",
];

#[derive(Default)]
struct ScanState {
    files: usize,
    directories: usize,
    skipped: usize,
    items: Vec<Item>,
    extensions: BTreeMap<String, usize>,
}

struct Item {
    path: String,
    kind: &'static str,
    extension: String,
    size: u64,
    readable: bool,
}

fn json_escape(value: &str) -> String {
    let mut escaped = String::new();
    for ch in value.chars() {
        match ch {
            '"' => escaped.push_str("\\\""),
            '\\' => escaped.push_str("\\\\"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            c if c.is_control() => escaped.push_str(&format!("\\u{:04x}", c as u32)),
            c => escaped.push(c),
        }
    }
    escaped
}

fn normalize_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn is_blocked_dir(path: &Path) -> bool {
    path.file_name()
        .and_then(|part| part.to_str())
        .map(|name| BLOCKED_DIRS.iter().any(|blocked| blocked.eq_ignore_ascii_case(name)))
        .unwrap_or(false)
}

fn extension(path: &Path) -> String {
    path.extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
}

fn is_readable_extension(ext: &str) -> bool {
    READABLE_EXTENSIONS.iter().any(|candidate| candidate == &ext)
}

fn walk(root: &Path, current: &Path, max_items: usize, state: &mut ScanState) {
    if state.items.len() >= max_items {
        return;
    }

    let entries = match fs::read_dir(current) {
        Ok(entries) => entries,
        Err(_) => {
            state.skipped += 1;
            return;
        }
    };

    for entry in entries.flatten() {
        if state.items.len() >= max_items {
            return;
        }

        let path = entry.path();
        let relative = match path.strip_prefix(root) {
            Ok(relative) => relative,
            Err(_) => continue,
        };

        let metadata = match entry.metadata() {
            Ok(metadata) => metadata,
            Err(_) => {
                state.skipped += 1;
                continue;
            }
        };

        if metadata.is_dir() {
            if is_blocked_dir(&path) {
                state.skipped += 1;
                continue;
            }

            state.directories += 1;
            state.items.push(Item {
                path: normalize_path(relative),
                kind: "directory",
                extension: String::new(),
                size: 0,
                readable: false,
            });
            walk(root, &path, max_items, state);
            continue;
        }

        if metadata.is_file() {
            let ext = extension(&path);
            let readable = is_readable_extension(&ext);
            state.files += 1;
            if !ext.is_empty() {
                *state.extensions.entry(ext.clone()).or_insert(0) += 1;
            }
            state.items.push(Item {
                path: normalize_path(relative),
                kind: "file",
                extension: ext,
                size: metadata.len(),
                readable,
            });
        }
    }
}

fn print_json(root: &Path, state: ScanState, max_items: usize) {
    let mut output = String::new();
    output.push_str("{");
    output.push_str(&format!("\"engine\":\"rust\","));
    output.push_str(&format!("\"root\":\"{}\",", json_escape(&root.to_string_lossy())));
    output.push_str(&format!("\"max_items\":{},", max_items));
    output.push_str(&format!("\"files\":{},", state.files));
    output.push_str(&format!("\"directories\":{},", state.directories));
    output.push_str(&format!("\"skipped\":{},", state.skipped));

    output.push_str("\"extensions\":{");
    for (index, (ext, count)) in state.extensions.iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!("\"{}\":{}", json_escape(ext), count));
    }
    output.push_str("},");

    output.push_str("\"items\":[");
    for (index, item) in state.items.iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!(
            "{{\"path\":\"{}\",\"type\":\"{}\",\"extension\":\"{}\",\"size\":{},\"readable\":{}}}",
            json_escape(&item.path),
            item.kind,
            json_escape(&item.extension),
            item.size,
            item.readable
        ));
    }
    output.push_str("]}");
    println!("{}", output);
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: eva-rust-indexer <path> [max_items]");
        std::process::exit(2);
    }

    let root = PathBuf::from(&args[1]);
    let max_items = args
        .get(2)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(500)
        .clamp(1, 5000);

    let root = match root.canonicalize() {
        Ok(path) => path,
        Err(_) => {
            eprintln!("Root path not found");
            std::process::exit(1);
        }
    };

    let mut state = ScanState::default();
    walk(&root, &root, max_items, &mut state);
    print_json(&root, state, max_items);
}
