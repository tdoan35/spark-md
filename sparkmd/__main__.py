def main():
    import uvicorn
    from .config import Config
    config = Config()
    # SSE clients stay connected indefinitely; bound graceful drain for restarts.
    uvicorn.run('sparkmd.app:app', host=config.bind, port=config.port,
                proxy_headers=False, timeout_graceful_shutdown=5)


if __name__ == '__main__':
    main()
