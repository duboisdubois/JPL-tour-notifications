import boto3
import time
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

# Configuration
TABLE_NAME = "JplTourCallHistory"
TEST_PHONE_NUMBER = "+15555555556"  # Replace with your actual phone number if testing with real data

def create_table_if_not_exists(dynamodb):
    """Create DynamoDB table if it doesn't exist"""
    try:
        # Check if table exists
        dynamodb.Table(TABLE_NAME).table_status
        print(f"Table {TABLE_NAME} already exists.")
        return True
    except ClientError:
        print(f"Creating table {TABLE_NAME}...")
        # Create table if it doesn't exist
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
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
        print("Waiting for table creation...")
        table.meta.client.get_waiter('table_exists').wait(TableName=TABLE_NAME)
        print(f"Table {TABLE_NAME} created successfully!")
        return True

def can_make_call(dynamodb, phone_number):
    """Check if we can make a call (15 min elapsed since last call)"""
    table = dynamodb.Table(TABLE_NAME)
    
    # Get the last call time
    response = table.get_item(
        Key={
            'phone_number': phone_number
        }
    )
    
    current_time = datetime.now()
    
    # If there's no record or it's been more than 15 minutes since the last call
    if 'Item' not in response:
        print(f"No previous call record found for {phone_number}")
        return True
    
    last_call_time = datetime.fromisoformat(response['Item']['last_call_time'])
    time_difference = current_time - last_call_time
    minutes_passed = time_difference.total_seconds() / 60
    
    print(f"Last call was made at: {last_call_time}")
    print(f"Time since last call: {minutes_passed:.2f} minutes")
    
    # Return True if more than 15 minutes have passed
    return time_difference > timedelta(minutes=15)

def update_last_call_time(dynamodb, phone_number):
    """Update the last call time in DynamoDB"""
    table = dynamodb.Table(TABLE_NAME)
    current_time = datetime.now()
    
    # Update the last call time
    table.put_item(
        Item={
            'phone_number': phone_number,
            'last_call_time': current_time.isoformat()
        }
    )
    print(f"Updated last call time to {current_time} for {phone_number}")

def mock_send_voice_call(dynamodb, phone_number):
    """Mock function to simulate making a Twilio call with rate limiting"""
    # Check if we can make a call
    if not can_make_call(dynamodb, phone_number):
        print("RATE LIMITED: Cannot make call - less than 15 minutes since last call")
        return False
    
    # Simulate making a call
    print("CALL MADE: Successfully simulated making a call to", phone_number)
    
    # Update the last call time in DynamoDB
    update_last_call_time(dynamodb, phone_number)
    return True

def clear_call_history(dynamodb, phone_number):
    """Clear the call history for testing purposes"""
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.delete_item(
            Key={
                'phone_number': phone_number
            }
        )
        print(f"Deleted call history for {phone_number}")
    except ClientError as e:
        print(f"Error deleting call history: {e}")

def run_test(test_number, dynamodb, phone_number, description, expected_result=None):
    """Run a single test with proper logging"""
    print(f"\n--- TEST {test_number}: {description} ---")
    result = mock_send_voice_call(dynamodb, phone_number)
    
    if expected_result is not None:
        if result == expected_result:
            print(f"✅ TEST {test_number} PASSED: Got expected result: {result}")
        else:
            print(f"❌ TEST {test_number} FAILED: Expected {expected_result}, got {result}")
    
    return result

def lambda_handler(event, context):
    """Main Lambda handler for running tests"""
    # Get the test type from the event
    test_type = event.get('test_type', 'full')
    phone_number = event.get('phone_number', TEST_PHONE_NUMBER)
    
    # Initialize DynamoDB
    dynamodb = boto3.resource('dynamodb')
    
    # Ensure the table exists
    create_table_if_not_exists(dynamodb)
    
    results = {
        'test_results': [],
        'overall_success': True
    }
    
    if test_type == 'reset':
        # Just reset the call history and exit
        clear_call_history(dynamodb, phone_number)
        return {
            'statusCode': 200,
            'body': 'Call history reset successfully'
        }
    
    if test_type == 'full' or test_type == 'test1':
        # Reset before Test 1
        clear_call_history(dynamodb, phone_number)
        
        # Test 1: First call should succeed
        test1_result = run_test(1, dynamodb, phone_number, "FIRST CALL (SHOULD SUCCEED)", True)
        results['test_results'].append({
            'test': 1,
            'description': 'First call with no history',
            'expected': True,
            'actual': test1_result,
            'passed': test1_result == True
        })
        if test1_result != True:
            results['overall_success'] = False
    
    if test_type == 'full' or test_type == 'test2':
        # Test 2: Immediate second call should be rate limited
        test2_result = run_test(2, dynamodb, phone_number, "IMMEDIATE SECOND CALL (SHOULD BE RATE LIMITED)", False)
        results['test_results'].append({
            'test': 2,
            'description': 'Second immediate call',
            'expected': False,
            'actual': test2_result,
            'passed': test2_result == False
        })
        if test2_result != False:
            results['overall_success'] = False
    
    if test_type == 'full' or test_type == 'test3':
        # Test 3: Manual time manipulation for testing purposes
        print("\n--- TEST 3: MANIPULATING TIMESTAMP TO SIMULATE TIME PASSING ---")
        
        # Set the timestamp to 16 minutes ago
        table = dynamodb.Table(TABLE_NAME)
        past_time = datetime.now() - timedelta(minutes=16)
        table.put_item(
            Item={
                'phone_number': phone_number,
                'last_call_time': past_time.isoformat()
            }
        )
        print(f"Modified last call time to {past_time} (16 minutes ago)")
        
        # Test 4: Call after 16 minutes should succeed
        test4_result = run_test(4, dynamodb, phone_number, "CALL AFTER 16 MINUTES (SHOULD SUCCEED)", True)
        results['test_results'].append({
            'test': 4,
            'description': 'Call after 16 minutes',
            'expected': True,
            'actual': test4_result,
            'passed': test4_result == True
        })
        if test4_result != True:
            results['overall_success'] = False
    
    if results['overall_success']:
        print("\n✅ ALL TESTS COMPLETED SUCCESSFULLY ✅")
    else:
        print("\n❌ SOME TESTS FAILED ❌")
    
    return {
        'statusCode': 200,
        'body': results
    }