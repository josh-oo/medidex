"""Process entrypoint: builds the REST API app this container serves.
"""

from fastapi_app import create_app

app = create_app()
