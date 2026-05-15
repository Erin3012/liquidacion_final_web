def application(environ, start_response):
    body = b"Liquidacion web: cPanel WSGI ok"
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]
