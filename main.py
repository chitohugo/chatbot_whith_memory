"""Entrada de consola para comprobar la disponibilidad de la API."""
from api_client import APIClient, APIError
from config import settings


def main():
    client = APIClient(settings.api.base_url)
    try:
        print(client.health())
    except APIError as error:
        raise SystemExit(f"API no disponible: {error.detail}") from error


if __name__ == "__main__":
    main()
