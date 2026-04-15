use pyo3::prelude::*;
use std::fs::OpenOptions;
use std::io::Write;
use pyo3::exceptions::PyIOError;
use walkdir::WalkDir;

#[pyfunction]
fn find_file(name: String, start: String) -> PyResult<Option<String>> {
    for entry in WalkDir::new(&start) {
    let entry = entry.map_err(|e| PyIOError::new_err(e.to_string()))?;
    if entry.file_name().to_string_lossy() == name {
        return Ok(Some(entry.path().to_string_lossy().to_string()));
        }
    }
    Ok(None)
}

#[pyfunction]
fn read_file(path: String) -> PyResult<String> {
    std::fs::read_to_string(&path)
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

#[pyfunction]
fn write_file(path: String, content: String) -> PyResult<()> {
    std::fs::write(&path, &content)
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

#[pyfunction]
fn append_file(path: String, content: String) -> PyResult<()> {
    let mut file = OpenOptions::new().append(true).open(&path)?;
    file.write_all(content.as_bytes())
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

#[pyfunction]
fn list_files(dir: String) -> PyResult<Vec<String>> {
    let entries = std::fs::read_dir(&dir)
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    
    let mut files = vec![];
    for entry in entries {
        let entry = entry.map_err(|e| PyIOError::new_err(e.to_string()))?;
        files.push(entry.file_name().to_string_lossy().to_string());
    }
    Ok(files)
}

#[pyfunction]
fn 	delete_file(path: String) -> PyResult<()> {
    std::fs::remove_file(&path)
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

#[pyfunction]
fn rename_file(from: String, to: String) -> PyResult<()> {
        std::fs::rename(&from, &to)
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

#[pymodule]
fn file_ops(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(read_file, m)?)?;
    m.add_function(wrap_pyfunction!(write_file, m)?)?;
    m.add_function(wrap_pyfunction!(append_file, m)?)?;
    m.add_function(wrap_pyfunction!(list_files, m)?)?;
    m.add_function(wrap_pyfunction!(file_exists, m)?)?;
    m.add_function(wrap_pyfunction!(delete_file, m)?)?;
    m.add_function(wrap_pyfunction!(rename_file, m)?)?;
        Ok(())
}