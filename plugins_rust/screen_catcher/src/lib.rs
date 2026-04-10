use pyo3::prelude::*;
use xcap::Monitor;
use base64::{engine::general_purpose::STANDARD, Engine};
use std::io::Cursor;

#[pyfunction]
fn capture_screen_base64() -> PyResult<String> {
    // Крок 1 — отримуємо монітори
    let monitors = Monitor::all()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    
    let monitor = monitors.into_iter().next()
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Монітор не знайдено"))?;
    
    // Крок 2 — робимо скріншот (в пам'ять, не на диск!)
    let image = monitor.capture_image()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    
    // Крок 3 — PNG байти в буфер (не файл, а Vec<u8> в пам'яті)
    let mut buf = Cursor::new(Vec::new());
    image.write_to(&mut buf, image::ImageFormat::Png)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    
    // Крок 4 — кодуємо в Base64
    let base64_str = STANDARD.encode(buf.into_inner());
    
    Ok(base64_str)
}

#[pymodule]
fn screen_catcher(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(capture_screen_base64, m)?)?;
    Ok(())
}