## @skip_on_github
## @pytest.mark.asyncio
## @patch("app.ae200.get_status", new_callable=AsyncMock)
## async def test_status_endpoint(mock_get_status, client): # Needs client to ensure DB setup
##     mock_get_status.return_value = [{'name':'test-device','drive':'ON','speed':'HIGH','val':4}]
##
##     # If this status endpoint also uses db.get_db_connection,
##     # it will now correctly use the overridden test DB.
##     response = client.get("/api/v1/status")
##     assert response.status_code == 200
##     response_json = response.json()
##     logging.info(" /status: %s", response_json)
##     assert "devices" in response_json
