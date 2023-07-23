from channels.middleware import BaseMiddleware

class WebSocketMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        if b'x-forwarded-for' in headers:
            # The client is behind a proxy.
            scope['client_ip'] = headers[b'x-forwarded-for'].decode('utf-8')
        else:
            # The client is not behind a proxy.
            scope['client_ip'] = scope['client'][0]
        return await super().__call__(scope, receive, send)
