def main():
    import uvicorn
    from .config import Config
    config = Config()
    uvicorn.run('sparkmd.app:app', host=config.bind, port=config.port, proxy_headers=False)


if __name__ == '__main__':
    main()
