use pyo3::prelude::*;
use pyo3::types::PyDict;
use sysinfo::System;

#[pyfunction]
fn get_stats(py: Python<'_>) -> PyResult<Py<PyDict>> {
    
    let mut sys = System::new_all();
    sys.refresh_all();
    
    // Ждём 200мс для подсчёта CPU delta
    std::thread::sleep(std::time::Duration::from_millis(200));
    sys.refresh_cpu_all();
    sys.refresh_memory();
    
    // Средняя нагрузка по всем ядрам
    let cpu_usage = sys.cpus()
        .iter()
        .map(|c| c.cpu_usage())
        .sum::<f32>()
        / sys.cpus().len() as f32;
    
    // % использования памяти
    let ram_usage = if sys.total_memory() > 0 {
        (sys.used_memory() as f32 / sys.total_memory() as f32) * 100.0
    } else {
        0.0
    };
    
        // Получаем температуру GPU через NVML (NVIDIA)
    let gpu_temp: Option<f32> = {
        use nvml_wrapper::Nvml;
        match Nvml::init() {
            Ok(nvml) => {
                match nvml.device_by_index(0) {
                    Ok(device) => {
                        match device.temperature(
                            nvml_wrapper::enum_wrappers::device::TemperatureSensor::Gpu
                        ) {
                            Ok(t) => Some(t as f32),
                            Err(_) => None,
                        }
                    }
                    Err(_) => None,
                }
            }
            Err(_) => None,
        }
    };

    let dict = PyDict::new(py);
    dict.set_item("cpu", (cpu_usage * 10.0).round() / 10.0)?;
    dict.set_item("ram", (ram_usage * 10.0).round() / 10.0)?;
    dict.set_item("gpu_temp", gpu_temp)?;
    
    Ok(dict.into())
}



// В pyo3 0.23 синтаксис #[pymodule] изменился
#[pymodule]
fn jarvis_stats(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_stats, m)?)?;
    Ok(())
}

