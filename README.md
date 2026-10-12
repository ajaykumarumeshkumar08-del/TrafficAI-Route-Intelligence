# 🚦 TrafficAI — Route Traffic Intelligence

TrafficAI is a Python-based web application that helps users
search for locations, calculate driving routes, and review
traffic-aware travel estimates.

The project also includes a separate Machine Learning demo
that analyses historical traffic patterns.

## ✨ Features

- Search starting locations and destinations
- Select the correct place from search results
- Calculate a driving route
- View route distance and estimated travel time
- Display reported traffic delay when available
- View an interactive route map
- Review recent route checks during the current session
- Explore historical traffic analytics
- Demonstrate a Random Forest traffic-volume prediction model

## 🛠️ Technologies Used

- Python
- Streamlit
- Pandas
- Scikit-learn
- Requests
- Folium
- Streamlit-Folium
- TomTom Search and Routing APIs
- OpenStreetMap map tiles

## 📂 Project Structure

```text
AI-Traffic-Predictor/
├── app.py
├── train_model.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── Metro_Interstate_Traffic_Volume.csv.gz
└── model/
    └── traffic_model.pkl (generated locally)
```

## Train the Machine Learning Model

The trained model file is excluded from GitHub because it exceeds
GitHub's standard file-size limit.

After installing the dependencies, run:

```powershell
python train_model.py
```