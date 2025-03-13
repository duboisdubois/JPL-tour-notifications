import os 
import requests
import time
import boto3
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth


# Twilio configuration
account_sid = os.environ.get("ACCOUNT_SID")
auth_token = os.environ.get("AUTH_TOKEN")
twilio_number = os.environ.get("TWILIO_NUMBER")
your_phone_number = os.environ.get("ALICE_PHONE_NUMBER")

# DynamoDB configuration
dynamodb = boto3.resource('dynamodb')
table_name = "JplTourCallHistory"

def create_table_if_not_exists():
    """Create DynamoDB table if it doesn't exist"""
    try:
        # Check if table exists
        dynamodb.Table(table_name).table_status
        return True
    except:
        # Create table if it doesn't exist
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'phone_number',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'phone_number',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 1,
                'WriteCapacityUnits': 1
            }
        )
        # Wait until the table exists
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
        return True

def can_make_call():
    """Check if we can make a call (15 min elapsed since last call)"""
    create_table_if_not_exists()
    table = dynamodb.Table(table_name)
    
    # Get the last call time
    response = table.get_item(
        Key={
            'phone_number': your_phone_number
        }
    )
    
    current_time = datetime.now()
    
    # If there's no record or it's been more than 15 minutes since the last call
    if 'Item' not in response:
        return True
    
    last_call_time = datetime.fromisoformat(response['Item']['last_call_time'])
    time_difference = current_time - last_call_time
    
    # Return True if more than 15 minutes have passed
    return time_difference > timedelta(minutes=15)

def update_last_call_time():
    """Update the last call time in DynamoDB"""
    table = dynamodb.Table(table_name)
    
    # Update the last call time
    table.put_item(
        Item={
            'phone_number': your_phone_number,
            'last_call_time': datetime.now().isoformat()
        }
    )

def send_voice_call():
    # Check if we can make a call
    if not can_make_call():
        print("Rate limit applied: Less than 15 minutes since last call")
        return
    
    # Twilio API endpoint for making a call
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json'
    print(your_phone_number)
    # Message to be read during the call
    message = "Hi Alice! There is a JPL tour available. Go get it! Good luck! You're a great mom, doing awesome things to help your kid have enriching experiences in middle school."

    # TwiML payload as XML (Twilio's Markup Language)
    twiml = f"""
    <Response>
        <Say voice="alice">{message}</Say>
    </Response>
    """

    # Data for the call request
    data = {
        'From': twilio_number,
        'To': your_phone_number,
        'Twiml': twiml
    }

    # Make the POST request to Twilio API with basic authentication
    response = requests.post(url, data=data, auth=HTTPBasicAuth(account_sid, auth_token))
    
    # Check if the request was successful
    if response.status_code == 201:
        print(f"Call SID: {response.json()['sid']}")
        # Update the last call time in DynamoDB
        update_last_call_time()
    else:
        print(f"Failed to make the call. Status Code: {response.status_code}")
        print(f"Error: {response.text}")
   

def check_jpl_tour_availability():
    url = 'https://www.jpl.nasa.gov/events/tours/api/tours/search'
    headers = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36', 'content-type': 'application/json'}
    r = requests.post(url, headers=headers, json={
        "category_id": "1",
        "group_size": "75",
        "pendingReservationId": None
        })

    data = r.json()

    public_tours = data["public_tours"]
    if len(public_tours) > 0:
        send_voice_call()

def lambda_handler(event, context):
    check_jpl_tour_availability()
    return {
        'statusCode': 200,
        'body': "OK"
    }