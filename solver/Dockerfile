FROM python:3.12-slim

WORKDIR /app

COPY solver/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY solver/app ./app
COPY solver/tests ./tests
COPY solver/pytest.ini ./pytest.ini
# The seed dataset is shared with the frontend; the solver's tests read it.
COPY shared /shared

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
