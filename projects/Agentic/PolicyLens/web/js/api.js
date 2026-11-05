// A single place for HTTP, timeouts and readable error messages.
export async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  try {
    const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
    const response = await fetch(`/api${path}`, { ...options, headers, signal: controller.signal });
    const raw = await response.text();
    let body;
    try { body = raw ? JSON.parse(raw) : null; }
    catch {
      throw new Error(response.ok ? "The server returned an unexpected response." : `The server could not complete the request (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      const message = typeof body?.detail === "string" ? body.detail : `The request failed (HTTP ${response.status}).`;
      throw new Error(message);
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The request took too long. Check the server before trying again.");
    if (error instanceof TypeError) throw new Error("Could not connect to PolicyLens. Check that the local server is running.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

