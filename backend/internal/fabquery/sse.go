package fabquery

import (
	"encoding/json"
	"fmt"
	"net/http"
)

func WriteSSEEvent(w http.ResponseWriter, event string, data interface{}) {
	payload, err := json.Marshal(data)
	if err != nil {
		return
	}
	// SSE spec: each event is terminated by a blank line (two \n).
	fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, payload)

	// Not all ResponseWriters implement Flusher (e.g. httptest.Recorder doesn't).
	// Without Flush the data sits in the buffer and the browser sees nothing until the connection closes.
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
}

func SetSSEHeaders(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/event-stream")  // define SSE
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")
}
