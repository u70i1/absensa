# Absensa - School Attendance System (Working Name!)

An ongoing project.

Contributions are welcomed! Please check out the to-do list below for current priorities.

## Current To-Do
- [ ] Add POST, PATCH, and DELETE /students endpoint
- [x] Add GET and DELETE /scan endpoint

<details>
  <summary>Previously Completed Tasks</summary>

  - [x] *~~Fix routes to work with Postgres like they did with CSV~~*
  - [x] *~~Initialize Postgres on Docker~~*
  - [x] *~~Migrate all mock CSV files to Postgres~~*
  - [x] *~~Initialize Alembic for database migrations~~*
</details>

## How to Run the Backend Server
This project isn't expected to run properly yet, but if you want to run it anyway (maybe you're planning to contribute, thank you!), follow these steps:

1. Clone this repository.

2. Configure `docker-compose.yml` to your liking, then spin up a PostgreSQL container with:
    ```
    docker compose up -d
    ```
    Once it's running, note the port you set under the `ports` key (5433 by default) -- you'll need it in the next step.

3. In the `backend` folder, copy `.env.example` to a new file named `.env`. Update the values as needed -- most importantly `DATABASE_URL`, which should match how you configured `docker-compose.yml`:
    ```
    DATABASE_URL="postgresql+psycopg2://POSTGRES_USER:POSTGRES_PASSWORD@localhost:port/attendance"
    ```

4. Set up a Python environment and install the dependencies from `requirements.txt`.

5. Run the initial Alembic migration:
    ```
    alembic upgrade head
    ```

6. That's it! The API is ready to run. Start it with `uvicorn`.

### Running Tests
To run the test suite with `pytest`, you'll need a local PostgreSQL install and a dedicated test database. Create it with:

```
createdb -h localhost -p 5433 -U attendance test_attendance
```
(Again, swap `5433` for whatever port you set in `docker-compose.yml`.)

This creates a `test_attendance` database, which `pytest` reads from an environment variable.

