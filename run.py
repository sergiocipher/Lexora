import uvicorn

if __name__ == "__main__":
    print("Starting Search Typeahead System Server on http://127.0.0.1:8080 ...")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)
