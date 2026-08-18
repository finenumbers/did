def test_import_xlsx_route_registers():
    """File() upload is registered at import; missing python-multipart crashes uvicorn."""
    from app.api.routes.regions import router

    paths = {getattr(route, "path", "") for route in router.routes}
    assert any(path.endswith("/import.xlsx") for path in paths)
