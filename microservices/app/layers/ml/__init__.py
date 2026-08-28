#-------------------------ml_layer----------------------------
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import IsolationForest
import pandas as pd

# frocing pandas to show entire dataframe in terminal
pd.set_option('display.max_columns', None)       # Show every column
pd.set_option('display.max_colwidth', None)      # Stop long text (like anomaly_reason) from getting cut off with "..."
pd.set_option('display.width', 2000)             # Expand the terminal width threshold to prevent awkward wrapping
#raw data 
df = pd.read_parquet("data/raw/aws_clean_baseline.parquet")
#--------------------------------------training----------------------------------------

features = ['temp_c', 'pressure_hpa', 'humidity_pct']
#extracting hours from. datetime so as to learn the day apttermn
df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
features.append('hour')

isolation_forest = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)#currrently expecting 1%data to be anomalous
isolation_forest.fit(df[features])

explainer=shap.TreeExplainer(isolation_forest)


#--------------------------------------model-------------------------------------------
def isolation_forest_shap(batch_df,model,explainer,features):
    result_df=pd.DataFrame()
    result_df["time"]=batch_df["timestamp"]
    result_df['station_id'] = batch_df['station_id']
    result_df['predicted_anomaly'] = 0 
    result_df['sensor_type'] = None
    result_df['anomaly_value'] = np.nan
    result_df['anomaly_reason'] = None
    result_df['expected_cause'] = 'Multivariate deviation from historical baseline'# to improve
    result_df['recommended_action'] = 'Check blamed sensor for calibration drift or transient faults'
    result_df['layer_used'] = 'Layer 2: ML (Isolation Forest + SHAP)'

    batch_features = batch_df[features]
    predictions = model.predict(batch_features)

    anom_idx = batch_df.index[predictions == -1]
    
    #shap
    if not anom_idx.empty:#so that  shap doent get a data with no anomalies
        # 3. updating the anomaly flag from 0 to 1 for the broken rows
        result_df.loc[anom_idx, 'predicted_anomaly'] = 1

        # shap
        shap_values = explainer.shap_values(batch_df.loc[anom_idx, features])

        for i, idx in enumerate(anom_idx):
            row_shap_values = shap_values[i]

            top_feature_idx = np.argmax(np.abs(row_shap_values))
            blamed_feature = features[top_feature_idx]

            result_df.loc[idx, 'sensor_type'] = blamed_feature
            result_df.loc[idx, 'anomaly_value'] = batch_df.loc[idx, blamed_feature]
            result_df.loc[idx, 'anomaly_reason'] = f"SHAP flagged '{blamed_feature}' as primary driver of the multivariate anomaly."
            
    return result_df
    


#-----------------------testing--------------------------
df_eval = pd.read_parquet('aws_evaluation_dataset.parquet')
df_eval['hour'] = pd.to_datetime(df_eval['timestamp']).dt.hour
test_batch=df_eval
ml_alerts=isolation_forest_shap(test_batch,isolation_forest,explainer,features)


#=============================================================================================================================
#-----------------------------------------------------------------------------------------------------------------------------


#-----------------------------gap_layer----------------------------


 
