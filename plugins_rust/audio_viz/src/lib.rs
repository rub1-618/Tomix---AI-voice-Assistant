use pyo3::prelude::*;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::SampleFormat;
use std::sync::{Arc, Mutex};

#[pymodule]
mod audio_viz {
    use super::*;

    #[pyfunction]
    fn get_volume() -> PyResult<f32> {
        let host = cpal::default_host();
        let device = host.default_input_device()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("No input device found"))?;
        let config = device.default_input_config()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let volume = Arc::new(Mutex::new(0.0f32));
        let volume_clone = Arc::clone(&volume);

        let stream = match config.sample_format() {
            SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    let rms = (data.iter().map(|s| s * s).sum::<f32>() / data.len() as f32).sqrt();
                    *volume_clone.lock().unwrap() = rms;
                },
                |err| eprintln!("Stream error: {}", err),
                None,
            ),
            _ => return Err(pyo3::exceptions::PyRuntimeError::new_err("Unsupported sample format")),
        }.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        stream.play()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        std::thread::sleep(std::time::Duration::from_millis(100));

        Ok(*volume.lock().unwrap())
    }

    #[pyfunction]
    fn get_input_devices() -> PyResult<Vec<String>> {
        let host = cpal::default_host();
        let devices = host.input_devices()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(devices.filter_map(|d| d.name().ok()).collect())
    }
}