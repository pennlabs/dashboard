// Forward /api to the Django backend during local development.
//
// This exists rather than the simpler `"proxy"` field in package.json because
// OAuth needs the *browser* to navigate to /api/accounts/login/ (and to be
// redirected back to /api/accounts/callback/). CRA's package.json proxy
// deliberately skips any request whose Accept header includes text/html, so
// those navigations would be served index.html instead of reaching Django.
// setupProxy.js has no such rule.
//
// Keeping everything on localhost:3000 also makes the whole flow same-origin,
// which is what lets the session and CSRF cookies work.
//
// http-proxy-middleware ships as a transitive dependency of react-scripts.
const { createProxyMiddleware } = require("http-proxy-middleware")

module.exports = function (app) {
  app.use(
    createProxyMiddleware("/api", {
      // 127.0.0.1, not localhost: Node resolves "localhost" to ::1 first, but
      // `manage.py runserver 127.0.0.1:8000` only listens on IPv4, so the
      // proxy would 504 on the first attempt.
      target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8000",
      // Preserve the Host header. Django builds the OAuth redirect_uri from the
      // request when LABS_REDIRECT_URI isn't set, and needs to see :3000.
      changeOrigin: false,
    })
  )
}
