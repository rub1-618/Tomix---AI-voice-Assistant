use pyo3::prelude::*;
use pyo3::types::PyDict;
use windows::Win32::UI::Input::KeyboardAndMouse::{keybd_event, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK, VK_MEDIA_PLAY_PAUSE};
use windows::Media::Control::GlobalSystemMediaTransportControlsSessionManager;
use pyo3::exceptions::PyIOError;


#[pyfunction]
fn get_media_info(py: Python<'_>) -> PyResult<Py<PyDict>> {
    // WinRT async → блокирующий вызов
    let manager = GlobalSystemMediaTransportControlsSessionManager
    ::RequestAsync()
    .map_err(|e| PyIOError::new_err(e.to_string()))?
    .get()
    .map_err(|e| PyIOError::new_err(e.to_string()))?;

    let session = manager.GetCurrentSession()
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    let props = session.TryGetMediaPropertiesAsync()
        .map_err(|e| PyIOError::new_err(e.to_string()))?
        .get()
        .map_err(|e| PyIOError::new_err(e.to_string()))?;

    let dict = PyDict::new(py);
    dict.set_item("title", props.Title()
        .map_err(|e| PyIOError::new_err(e.to_string()))?.to_string())?;
    dict.set_item("artist", props.AlbumArtist()
        .map_err(|e| PyIOError::new_err(e.to_string()))?.to_string())?;
    Ok(dict.into())
}


#[pyfunction]
fn toggle_play_pause() {
    unsafe {
        keybd_event(VK_MEDIA_PLAY_PAUSE.0 as u8, 0, KEYBD_EVENT_FLAGS(0), 0);
        keybd_event(VK_MEDIA_PLAY_PAUSE.0 as u8, 0, KEYEVENTF_KEYUP, 0);
    }
}

#[pyfunction]
fn next_track() {
    unsafe {
        keybd_event(VK_MEDIA_NEXT_TRACK.0 as u8, 0, KEYBD_EVENT_FLAGS(0), 0);
        keybd_event(VK_MEDIA_NEXT_TRACK.0 as u8, 0, KEYEVENTF_KEYUP, 0);
    }
}

#[pyfunction]
fn prev_track() {
    unsafe {
        keybd_event(VK_MEDIA_PREV_TRACK.0 as u8, 0, KEYBD_EVENT_FLAGS(0), 0);
        keybd_event(VK_MEDIA_PREV_TRACK.0 as u8, 0, KEYEVENTF_KEYUP, 0);
    }
}

// В pyo3 0.23 синтаксис #[pymodule] изменился
#[pymodule]
fn media_ctrl(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_media_info, m)?)?;
    m.add_function(wrap_pyfunction!(toggle_play_pause, m)?)?;
    m.add_function(wrap_pyfunction!(next_track, m)?)?;
    m.add_function(wrap_pyfunction!(prev_track, m)?)?;
    Ok(())
}
