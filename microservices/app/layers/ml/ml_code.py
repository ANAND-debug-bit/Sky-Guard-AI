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
#adding gaps in subsequent values to enable time awareness as gap is time independent but values are time dependent like day or night
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.sort_values(['station_id', 'timestamp'])
df['temp_jump'] = df.groupby('station_id')['temp_c'].diff().fillna(0)
df['pressure_jump'] = df.groupby('station_id')['pressure_hpa'].diff().fillna(0)
df['hour'] = df['timestamp'].dt.hour

features = ['temp_c', 'pressure_hpa', 'humidity_pct', 'hour', 'temp_jump', 'pressure_jump']
def train_model(df, features):
    isolation_forest = IsolationForest(n_estimators=100, contamination="auto", random_state=42)  # changed contamination to auto from 1%
    isolation_forest.fit(df[features])
    explainer = shap.TreeExplainer(isolation_forest)
    return isolation_forest, explainer
#---------------------------------------------------
isolation_forest = IsolationForest(n_estimators=100, contamination="auto", random_state=42)#changed contamination to auto from 1% 
isolation_forest.fit(df[features])
explainer=shap.TreeExplainer(isolation_forest)
#--------------------------------------model-------------------------------------------
def isolation_forest_shap(batch_df,model,explainer,features):
    result_df=pd.DataFrame()
    result_df["time"]=batch_df["timestamp"]
    result_df['station_id'] = batch_df['station_id']
    #-------adding is_anomaly col in resultant daatset
    if 'is_anomaly' in batch_df.columns:
        result_df['is_anomaly'] = batch_df['is_anomaly']


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
df_eval['timestamp'] = pd.to_datetime(df_eval['timestamp'])
df_eval = df_eval.sort_values(['station_id', 'timestamp'])
df_eval['temp_jump'] = df_eval.groupby('station_id')['temp_c'].diff().fillna(0)
df_eval['pressure_jump'] = df_eval.groupby('station_id')['pressure_hpa'].diff().fillna(0)
df_eval['hour'] = df_eval['timestamp'].dt.hour
#----------------
test_batch=df_eval
# ml_alerts=isolation_forest_shap(test_batch,isolation_forest,explainer,features)
# print(ml_alerts[ml_alerts["predicted_anomaly"]==1].head())

#=============================================================================================================================
#-----------------------------------------------------------------------------------------------------------------------------


#-----------------------------gap_layer---------------------------

def gap_detection(batch_df, sensor_columns):
    result_df = pd.DataFrame()
    result_df['time'] = batch_df['timestamp'] 
    result_df['station_id'] = batch_df['station_id']
    result_df['predicted_anomaly'] = 0 
    result_df['sensor_type'] = None
    result_df['anomaly_value'] = np.nan
    result_df['anomaly_reason'] = None
    result_df['expected_cause'] = None
    result_df['recommended_action'] = "expected value using chronos 2" #suggest expected value using chronos 2 layer
    result_df['layer_used'] = 'Layer 3: Gap(Null values)'

    missing_mask = batch_df[sensor_columns].isna().any(axis=1)
    anom_idx = batch_df.index[missing_mask]
    
    if not anom_idx.empty:
        result_df.loc[anom_idx, 'predicted_anomaly'] = 1
        result_df.loc[anom_idx, 'anomaly_reason'] = 'Missing value (np.nan)'
        #figuring out whether its a station fault (power cut) or single sensor(theft/wire fault)
        for idx in anom_idx:

            missing_cols = batch_df.loc[idx, sensor_columns].isna()
            blamed_features = missing_cols[missing_cols].index.tolist()#this methiod is used to pass a boolean sequence into itself to diplay only true values, and hence we stored those columns into list

            if len(blamed_features) == len(sensor_columns):
                #all sensors are dead
                result_df.loc[idx, 'sensor_type'] = 'ALL_SENSORS'
                result_df.loc[idx, 'expected_cause'] = 'Complete station power cut or data logger failure'

            else:
                #specific sensor(s) issue
                result_df.loc[idx, 'sensor_type'] = ", ".join(blamed_features)
                result_df.loc[idx, 'expected_cause'] = 'Individual sensor theft, disconnection, or failure'

    return result_df

#--------------------------------testing-------------------------------------------------------------------
# sensor_columns=['temp_c', 'pressure_hpa', 'humidity_pct']
# gap_result=gap_detection(test_batch,sensor_columns)
# print(gap_result[gap_result['predicted_anomaly']==1].head())

#================================================================================================
#---------------------------------------------------------------------------------------------------



#------------------------Ageing Layer---------------------------------------------------------------

#theory is that sensors degrade after long time due to heat/dust/other factors and it begins to drift the readings a bit  higher/lower than the actual value and that drift becomes large after a long period amnd sesnor then needs to be replaced/repaired
#mann kendal test will allow us to figure out whjether the sensor is degrading without caring about shpe of data by simply checking if in each pair, the next value is more or less then the previous value and give a score of =1 and -1 resp
# now if sensor is working fine, then the score over longer period will average out to be 0 but if its degrading then score ove rlonger period will be either highly positive or highly -ve 
#on this basis, we get a p-value and if p<0.05 then it means that pattern isnt random noise rather actual degradation
#after this we need to figure ouit by what speed is the data drifting to fin the no. of days after which we should do maintenance for which we sue sen's slope
#in sen's slope , we calculate the derivative by taking all possible pairs avaialble in our data and take its media to get median slope of the grap[h, this prevents the skewness of derivative by any outlier
#this derivative tells us by what amount does the reading drift on a usual day and we use it to find total drift over severral days
#finally we figure out the days remaining by creationg a max allowed drift so (max allowed drift-current drift)/sen's slope=no. of days till maintenance neeeded


#max allowed drifts acc to wmo and industrial standard
#temp_sensor=0.5 degree C
#pressure_sensor=0.5hpa
#rh sensor=5%

#code
#drift is basically error (the y_error in y=y_trend+y_seasonal+y_error)
drift_thresholds={"temp_c":0.5,"pressure_hpa":0.5,"humidity_pct":5.0}
import pymannkendall as mk
def sensor_health(sensor_series,sensor_name):
    max_allowable_drift = drift_thresholds.get(sensor_name, 2.0)#keeping a default threshold of 2 units in case a new sensor is added later
    #test,trend,and slope
    mk_result = mk.original_test(sensor_series)
    trend = mk_result.trend
    slope = mk_result.slope
    intercept=mk_result.intercept#needed as the formula to find total drift using ssen's slope needs the initial drift too

    #current drift
    total_days_active = len(sensor_series)
    current_drift=abs((total_days_active*slope)+intercept)

    #health bar/percentage
    health_percentage=max(0,100*(1-current_drift/max_allowable_drift))
    health_percentage=round(health_percentage,2)

    #defining health zones
    if health_percentage>=75:
        zone="Great Condition"
    elif health_percentage>=40:
        zone="Maintenance Recommended"
    else:
        zone="Crtical Condition, Urgent Maintenence required"

    #calculating days until maintenance needed
    if trend!="no trend" and slope !=0:
        remaining_drift_allowance=max_allowable_drift-current_drift
        days_until_maintenance=int(remaining_drift_allowance/abs(slope))
        days_until_maintenance=max(0,days_until_maintenance)
    else:
        days_until_maintenance="stable-no maintenance required"
    return {"Sensor":sensor_name,"Trend":trend,"Drift_Rate_per_day":round(abs(slope),5),"Health_Percentage":health_percentage,"Zone":zone,"Days_until_maintenance_necessary":days_until_maintenance}


#=====================================================================================================================================================================
#----------------------------------------------------------------------------------------------------------------------------------------

#--------------------------time series decomposition---------------------------------------------------------------------------------------------------------------

#now we need data in daily format for mann kendall and we should remove the weather influence and seasonal influence as seasons will mke readings like temo dec or inc ove rfew months but that isnt sensor degradation
# a given reading y can be written as y=y_trend+y_seasonal+y_error
def extract_daily_error(hourly_df,sensor_col):
    df = hourly_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').set_index('timestamp')

    #calculating daily average
    raw_daily_mean = df[sensor_col].resample('D').mean()

    #calculating seasonal influence using 30 day moving average
    seasonal_baseline = raw_daily_mean.rolling(window=30, min_periods=1).mean()#currentlky using min period 1 so as to start only when we have 30 day datat atleast
    #calculating the y_error
    daily_error=raw_daily_mean-seasonal_baseline
    return daily_error.dropna()


# now we have y_error for each day

#theory: now in case of mann kendall test, sensors degrade so they give reading greater than or elss than actual reading and that error tends to inc/decrease which the test measures and sen's slope finds out how fast that error is changing
#so we should pass the errors to mann kendal test for ageing layer
#very_important, pls read everyone: we calculated current drift in mann kendal as total active days*sen's slope +intercept(that is the initial error/drift) but we coud have directly used the error in tahty particular index in our input erro seriues as error itself is the drift, but assume we have a bird sitting on the sensor one day , now the reading would deviate largely and the current rerading would skyrocket and the health percentage will drop to 0 instantly
#to prevent this we used sen's sloppe as it'll caklcylate the median change in errors and hence ignore outliers and thne calculate final overall error using above formula

def maintenance_report(hourly_df,sensors):
    reports=[]

    for station in hourly_df['station_id'].unique():
        #getting the stationwise dataframe
        station_df=hourly_df[hourly_df["station_id"]==station]

        for sensor in sensors:
            daily_error=extract_daily_error(station_df,sensor)

            #setting a prerequisite of more than 3 day data else mann kendall wont be meaningful
            if len(daily_error)>3:
                report=sensor_health(daily_error,sensor)

                report["Station_ID"]=station
                reports.append(report)
            else:
                pass
    #rearranging to put station id in 1st column
    df_reports=pd.DataFrame(reports)
    cols=['Station_ID']+[col for col in df_reports if col != 'Station_ID']
    return df_reports[cols]


#--------------testing on actual data to hsow actual sensor degradation(big thing to show to judges speerately that current sesnors need maintenance and we detect it with days)

df = pd.read_parquet("data/raw/aws_clean_baseline.parquet")
sensors=['temp_c','pressure_hpa','humidity_pct']
health_data=maintenance_report(df,sensors)
# print(health_data)
#------------the data is really interesting(its run on real data, see present condition of sensors , we can use that in our pitch showing flaws in present infra)



from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

def evaluate_ml_layer(ml_results_df, true_label_col='is_anomaly'):
    """
    Calculates enterprise-grade performance metrics for the Isolation Forest layer.
    Requires a ground truth column in the evaluation dataset to compare against.
    """
    # Check if the dataset actually has a column telling us what was a real anomaly
    if true_label_col not in ml_results_df.columns:
        return f"Error: Ground truth column '{true_label_col}' not found in the dataframe."
    
    y_true = ml_results_df[true_label_col]
    y_pred = ml_results_df['predicted_anomaly']
    
    metrics = {
        "Accuracy (%)": round(accuracy_score(y_true, y_pred) * 100, 2),
        "Precision (%)": round(precision_score(y_true, y_pred, zero_division=0) * 100, 2),
        "Recall (%)": round(recall_score(y_true, y_pred, zero_division=0) * 100, 2),
        "F1-Score (%)": round(f1_score(y_true, y_pred, zero_division=0) * 100, 2)
    }
    
    return pd.DataFrame([metrics])

df_eval = pd.read_parquet('aws_evaluation_dataset.parquet')

# --- Calculating the jumps for the evaluation dataset ---
df_eval['timestamp'] = pd.to_datetime(df_eval['timestamp'])
df_eval = df_eval.sort_values(['station_id', 'timestamp'])
df_eval['temp_jump'] = df_eval.groupby('station_id')['temp_c'].diff().fillna(0)
df_eval['pressure_jump'] = df_eval.groupby('station_id')['pressure_hpa'].diff().fillna(0)
df_eval['hour'] = df_eval['timestamp'].dt.hour
# ------------------------------------------------------

ml_alerts = isolation_forest_shap(df_eval, isolation_forest, explainer, features)
ml_metrics = evaluate_ml_layer(ml_alerts, true_label_col='is_anomaly') # Change 'is_anomaly' if named differently
# print("\n--- ML Layer 2 Performance Metrics ---")
# print(ml_metrics)