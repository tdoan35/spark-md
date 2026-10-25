// Push-to-talk capture worklet (09-voice.md). Served same-origin from public/ so the
// page CSP (script-src 'self') allows addModule. Each 128-frame input block is posted
// to the main thread as a Float32Array copy; the main thread owns rate + WAV encoding.
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch && ch.length) this.port.postMessage(ch)
    return true
  }
}
registerProcessor("sparkmd-capture", CaptureProcessor)
