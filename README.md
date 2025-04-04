# FastAPI ESP Module Integration

This project is a FastAPI application designed to connect with an ESP module to monitor vehicle battery information and configure the relays on the board.

## Endpoints

### 1. **POST /login**
   - **Description**: Authenticates a user and provides a JWT token.
   - **Request Body**: JSON object with `username` and `password`.
   - **Response**: JSON object containing the access token and user details.

### 2. **POST /register**
   - **Description**: Registers a new user (protected endpoint).
   - **Request Body**: JSON object with `username` and `password`.
   - **Response**: Confirmation message for successful registration.

### 3. **POST /configure**
   - **Description**: Sends configuration parameters to the ESP module (protected endpoint).
   - **Request Body**: JSON object with configuration parameters (e.g., `device_id`, `relay1_time`, `relay2_time`, `min_voltage`).
   - **Response**: Confirmation of the configuration sent.

### 4. **GET /status**
   - **Description**: Retrieves the latest status of the device (protected endpoint).
   - **Response**: JSON object containing device status, including battery voltage, relay states, and timestamps.

## Running the Application

To run the application, you need to have Python installed. Follow these steps:

1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the application using Uvicorn:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. Access the API documentation at:
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Dependencies

The application requires the following Python packages:

- **FastAPI**: For building the API.
- **Uvicorn**: ASGI server to run the application.
- **Pydantic**: For data validation and settings management.
- **SQLAlchemy**: For database interactions.
- **Passlib**: For password hashing.
- **PyJWT (jose)**: For JWT token management.
- **PySerial**: For serial communication.
- **Paho-MQTT**: For MQTT communication.

Install all dependencies using the `requirements.txt` file provided in the project.

## Notes

- Ensure the ESP module is properly connected and configured to communicate with the application.
- Update the configuration file (if any) to match your ESP module's settings.

