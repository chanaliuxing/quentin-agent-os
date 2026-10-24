# scripts/run_api_server.py
import uvicorn


def main() -> None:
    uvicorn.run(
        "meta_agent.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发期方便
    )


if __name__ == "__main__":
    main()
