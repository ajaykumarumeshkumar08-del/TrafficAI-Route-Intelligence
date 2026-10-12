import pandas as pd
import pickle
import os

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# Load historical traffic data
df = pd.read_csv(
    "data/Metro_Interstate_Traffic_Volume.csv.gz",
    compression="gzip"
)

# Extract time features
df["date_time"] = pd.to_datetime(df["date_time"])
df["hour"] = df["date_time"].dt.hour
df["day_of_week"] = df["date_time"].dt.dayofweek
df["month"] = df["date_time"].dt.month

# Train using only time features
features = ["hour", "day_of_week", "month"]
X = df[features]
y = df["traffic_volume"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestRegressor(
    n_estimators=100,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

predictions = model.predict(X_test)

print("Model training completed!")
print(f"MAE: {mean_absolute_error(y_test, predictions):.2f}")
print(f"R2 Score: {r2_score(y_test, predictions):.2f}")

os.makedirs("model", exist_ok=True)

with open("model/traffic_model.pkl", "wb") as file:
    pickle.dump(model, file)

print("Updated model saved successfully!")