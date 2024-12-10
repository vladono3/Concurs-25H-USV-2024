import threading
import time
import os
import json
import serial
import openai
import ast
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, FastAPI
import psycopg2
from psycopg2 import pool
import atexit
from pydantic import BaseModel
from threading import Lock


class SensorCoordinates(BaseModel):
    lat: float
    lng: float


# Set your API key using environment variables
openai_secretkey = os.environ.get("CHAT_SECRET_KEY")
openai.api_key = os.environ.get("OPENAI_API_KEY", openai_secretkey)

# Initialize serial connection
ser = serial.Serial('COM9', 115200, timeout=1)

# Create a router for the sensors endpoint
sensors_router = APIRouter()

# Create a connection pool
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=20,  # Adjust as needed
    dbname=os.environ["dbname"],
    user=os.environ["user"],
    password=os.environ["password"],
    host=os.environ["host"],
    port=os.environ["port"]
)

# Persistent database connection
persistent_conn = None
conn_lock = Lock()


# Function to initialize a persistent connection
def init_db_connection():
    global persistent_conn
    with conn_lock:
        if not persistent_conn or persistent_conn.closed != 0:
            if persistent_conn:
                persistent_conn.close()
            persistent_conn = db_pool.getconn()


# Function to close all connections when the program exits
def close_db_pool():
    with conn_lock:
        if persistent_conn:
            persistent_conn.close()
        if db_pool:
            db_pool.closeall()


# Register the exit handler to close connections
atexit.register(close_db_pool)

# Initialize the persistent connection at startup
init_db_connection()

# Initialize the FastAPI app
app = FastAPI()

# Include the router
app.include_router(sensors_router)


@sensors_router.get("/sensors")
def get_sensors_position():
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                cur.execute("SELECT id, name, lat, lng FROM sensors")
                sensors = cur.fetchall()
                sensors_list = [{"id": row[0], "name": row[1], "lat": row[2], "lng": row[3]} for row in sensors]
        return {"sensors": sensors_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sensors_router.get("/sensors/live")
def get_sensors_live():
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                now = datetime.now()
                current_minute = now.hour * 60 + now.minute
                cur.execute("SELECT sensor1, noise FROM minute_data WHERE id = %s;", (current_minute,))
                result = cur.fetchone()
                if result:
                    sensor1_data, noise_data = result
                    sensor1_data.append(noise_data)
                    return {
                        "sensor1": sensor1_data
                    }
                else:
                    return {"detail": "No data available for the current minute"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sensors_router.post("/sensors")
def create_sensor(data: SensorCoordinates):
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                cur.execute("SELECT nextval('sensors_sequence')")
                sensor_id = cur.fetchone()[0]
                sensor_name = f"Sensor {sensor_id}"

                cur.execute("""
                    INSERT INTO sensors (id, name, lat, lng)
                    VALUES (%s, %s, %s, %s)
                """, (sensor_id, sensor_name, data.lat, data.lng))

                if sensor_id <= 2:
                    sensor_command = f'activate sensor {sensor_id}'
                    ser.write(sensor_command.encode())

                persistent_conn.commit()

        return get_sensors_position()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sensors_router.get("/sensors/ai")
def get_sensor_position():
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                cur.execute("SELECT id, name, lat, lng FROM sensors")
                sensors = cur.fetchall()
                sensors_list = [{"id": row[0], "name": row[1], "lat": row[2], "lng": row[3]} for row in sensors]

        prompt = (f"Given the following sensors data placement on the Google Maps map{sensors_list}, "
                  "determine the future position for the next sensor placement on the map. "
                  "Respond with only a JSON object that includes the latitude, longitude, and the reason for choosing this position. "
                  "The JSON should be formatted like this:"
                  '{"lat": given_position, "lng": given_position, "reason": "a reason why you chose this"}')

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response['choices'][0]['message']['content']
        response_dict = ast.literal_eval(response_text)

        returned_body = {
            "reason": response_dict["reason"],
            "lat": response_dict["lat"],
            "lng": response_dict["lng"]
        }

        return returned_body
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sensors_router.get("/tips/ai")
def get_tips():
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, lat, lng FROM sensors")
                sensors = cur.fetchall()
                sensors_list = [{"id": row[0], "name": row[1], "lat": row[2], "lng": row[3]} for row in sensors]

        # Format the input to send to OpenAI
        prompt = (
            "I want you to generate realistic data for every day of the past 365 days. For each sensor's location I want an average temperature, humidity, air quality and noise pollution. This would be an example {24, 94, 73, 67} would be 24 degrees, 94% humidity, 73dB and an AQI of 67. Generate realistic data for every sensor on every day."
            f"And here are the coordinates of each sensor's location {sensors_list}"

            "Use the generated data to return me an area where the city would benefit most from adding trees to help with pollution."
            "Also return an area where the city would benefit most from adding mist sprayers to help with temperature and humidity."
            "Also return an area where the city would benefit most from adding noise reduction laws to help with noise pollution."
            "These areas need to consist of 3 coordinates of it's corners. The area will be a poligon."
            
            "Respond with only a JSON object that includes the name of the area, the coordinates of the area's corners, and the reason for choosing this area. "
            "Make sure that the coordinates provided by you don t overlap each other and also provide best solutions."
            "The JSON should be formatted like this:"
            '[{"name":"trees","polygon":[[47.6412,26.20056],[47.64125,26.22267],[47.64374,26.22158]],"reason":"a short reason for why you chose this area"},{"name":"mist","polygon":[[47.642,26.201],[47.6425,26.2235],[47.644,26.222]],"reason":"a short reason for why you chose this area"},{"name":"noise","polygon":[[47.64,26.199],[47.6405,26.221],[47.642,26.22]],"reason":"a short reason for why you chose this area"}]')

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response['choices'][0]['message']['content']

        # Make sure the response format is valid JSON
        try:
            response_list = ast.literal_eval(response_text)

            # Validate the structure
            if isinstance(response_list, list) and all(
                    isinstance(item, dict) and
                    'name' in item and
                    'polygon' in item and
                    'reason' in item for item in response_list
            ):
                # Format the response to return it in the required format
                returned_body = [{"name": item["name"], "polygon": item["polygon"], "reason": item["reason"]} for item
                                 in response_list]

                return returned_body
            else:
                raise HTTPException(status_code=500, detail="Invalid response format from OpenAI.")
        except (ValueError, SyntaxError) as e:
            raise HTTPException(status_code=500, detail="Error parsing OpenAI response.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def update_minute_data(json_data):
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                now = datetime.now()
                minute_of_day = now.hour * 60 + now.minute

                sensor1_temp = json_data["sensor 1"]["temperature"]
                sensor1_humidity = json_data["sensor 1"]["humidity"]
                noise = json_data["noise"]
                cur.execute("""
                    UPDATE minute_data
                    SET sensor1 = ARRAY[%s, %s]::FLOAT[],
                        noise = %s
                    WHERE id = %s
                """, (sensor1_temp, sensor1_humidity, noise, minute_of_day))
                persistent_conn.commit()
    except Exception as e:
        print("Error updating minute_data:", str(e))


def listen_for_json():
    last_update = datetime.now()
    update_interval = timedelta(seconds=5)

    while True:
        if ser.in_waiting > 0:
            data = ser.readline().decode('utf-8').strip()
            if data:
                try:
                    json_data = json.loads(data)
                    if datetime.now() - last_update >= update_interval:
                        update_minute_data(json_data)
                        last_update = datetime.now()
                except json.JSONDecodeError:
                    print("Received data is not valid JSON:", data)
        time.sleep(0.1)


listener_thread = threading.Thread(target=listen_for_json, daemon=True)
listener_thread.start()


@sensors_router.get("/reports/daily")
def get_daily_reports():
    try:
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary
            with persistent_conn.cursor() as cur:
                today = datetime.now()
                first_day_of_month = today.replace(day=1)
                start_date = max(first_day_of_month, today - timedelta(days=7))
                start_day_of_year = start_date.timetuple().tm_yday
                end_day_of_year = today.timetuple().tm_yday

                cur.execute("""
                    SELECT id, sensor1, sensor2, sensor3, sensor4, sensor5
                    FROM year_data
                    WHERE id BETWEEN %s AND %s
                    ORDER BY id ASC;
                """, (start_day_of_year, end_day_of_year))

                rows = cur.fetchall()
                data = []

                for row in rows:
                    day_of_year = row[0]
                    date_for_day = datetime(datetime.now().year, 1, 1) + timedelta(days=day_of_year - 1)
                    formatted_date = date_for_day.strftime("%d.%m.%Y")

                    data.append({
                        "day_of_year": formatted_date,
                        "sensors": row[1:]
                    })

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sensors_router.get("/reports/monthly")
def get_monthly_reports():
    try:
        # Ensure the database connection is active
        with conn_lock:
            if persistent_conn.closed != 0:
                init_db_connection()  # Reconnect if necessary

            # Query the database to get monthly report data, ordered by month name
            with persistent_conn.cursor() as cur:
                current_year = datetime.now().year

                cur.execute("""
                    SELECT 
                        TO_CHAR(date_trunc('month', (DATE '2024-01-01' + (id - 1) * INTERVAL '1 day')), 'Month') AS month,
                        AVG(sensor1[1]) AS avg_sensor1_temp,
                        AVG(sensor1[2]) AS avg_sensor1_humidity,
                        AVG(sensor1[3]) AS avg_sensor1_noise,
                        AVG(sensor1[4]) AS avg_sensor1_air_quality,
                        AVG(sensor2[1]) AS avg_sensor2_temp,
                        AVG(sensor2[2]) AS avg_sensor2_humidity,
                        AVG(sensor2[3]) AS avg_sensor2_noise,
                        AVG(sensor2[4]) AS avg_sensor2_air_quality,
                        AVG(sensor3[1]) AS avg_sensor3_temp,
                        AVG(sensor3[2]) AS avg_sensor3_humidity,
                        AVG(sensor3[3]) AS avg_sensor3_noise,
                        AVG(sensor3[4]) AS avg_sensor3_air_quality,
                        AVG(sensor4[1]) AS avg_sensor4_temp,
                        AVG(sensor4[2]) AS avg_sensor4_humidity,
                        AVG(sensor4[3]) AS avg_sensor4_noise,
                        AVG(sensor4[4]) AS avg_sensor4_air_quality,
                        AVG(sensor5[1]) AS avg_sensor5_temp,
                        AVG(sensor5[2]) AS avg_sensor5_humidity,
                        AVG(sensor5[3]) AS avg_sensor5_noise,
                        AVG(sensor5[4]) AS avg_sensor5_air_quality
                    FROM year_data
                    WHERE id BETWEEN 1 AND 365
                    GROUP BY TO_CHAR(date_trunc('month', (DATE '2024-01-01' + (id - 1) * INTERVAL '1 day')), 'Month')
                    ORDER BY TO_DATE(TO_CHAR(date_trunc('month', (DATE '2024-01-01' + (id - 1) * INTERVAL '1 day')), 'Month'), 'Month');
                """)

                # Fetch the results from the query
                rows = cur.fetchall()

        # Prepare the structured data for the response
        data = []
        for row in rows:
            # Initialize sensor data, using zeros if values are None
            sensors_data = [
                [row[1] if row[1] is not None else 0, row[2] if row[2] is not None else 0,
                 row[3] if row[3] is not None else 0, row[4] if row[4] is not None else 0],
                [row[5] if row[5] is not None else 0, row[6] if row[6] is not None else 0,
                 row[7] if row[7] is not None else 0, row[8] if row[8] is not None else 0],
                [row[9] if row[9] is not None else 0, row[10] if row[10] is not None else 0,
                 row[11] if row[11] is not None else 0, row[12] if row[12] is not None else 0],
                [row[13] if row[13] is not None else 0, row[14] if row[14] is not None else 0,
                 row[15] if row[15] is not None else 0, row[16] if row[16] is not None else 0],
                [row[17] if row[17] is not None else 0, row[18] if row[18] is not None else 0,
                 row[19] if row[19] is not None else 0, row[20] if row[20] is not None else 0]
            ]

            # Remove trailing spaces from month names
            data.append({
                "month": row[0].strip(),
                "sensors": sensors_data
            })

        return data
    except Exception as e:
        # Handle any errors that occur during the process
        raise HTTPException(status_code=500, detail=str(e))


# Start the FastAPI application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
