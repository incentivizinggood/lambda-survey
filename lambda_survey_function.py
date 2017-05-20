import os
import urllib
import random

import boto3

from boto3.session import Session
from boto3.dynamodb.conditions import Key
from twilio.twiml.messaging_response import MessagingResponse

from question import *
from question_response import *

# Add S3 and DynamoDB session
s3 = boto3.resource('s3')
session = Session()

# Add Twilio credentials
account_sid = os.environ['ACCOUNT_SID']
auth_token = os.environ['AUTH_TOKEN']

# Add DynamoDB
dynamodb = boto3.resource('dynamodb','us-west-2')
table_users = dynamodb.Table('User_Data')

def lambda_handler(event, context):
    response = MessagingResponse()
    print('Event:', event)
    identify_key = 'Survey_Code'

    message = urllib.parse.unquote(event['Body'])
    from_number = event['From']
    num_media = event['NumMedia']

    from_number = urllib.parse.unquote(from_number)

    # Check the database for an existing user
    dynamo_response = table_users.query(KeyConditionExpression=Key('Survey_Code').eq(from_number))

    if dynamo_response['Count'] == 0:
        response.message("Error: We don't recognize your number")
        save_message = False
    else:
        save_message = True

    user = table_users.get_item(Key={identify_key: from_number})['Item']
    # Checks for initial response from survey deployment
    has_responded = user['Responded']
    if not has_responded:
        table_users.update_item(Key={identify_key: from_number, }, UpdateExpression="set Responded = :r",
                                ExpressionAttributeValues={':r': 1}, ReturnValues="UPDATED_NEW")
        has_responded = 1

    # Checks for command
    previous = (message == '<<')

    # Stores the response in the database
    if not previous:
        if save_message:
            # Handles storing media sent via text
            if num_media != '0':
                pic_url = urllib.parse.unquote(event['MediaUrl0'])
                twilio_pic = urllib.request.Request(pic_url, headers={'User-Agent': "Magic Browser"})
                image = urllib.request.urlopen(twilio_pic)
                image_bucket = 'image-monster'
                key = "ingest-images/" + str(from_number.replace('+', '')) + "/" + str(random.getrandbits(50)) + ".png"
                store_url = "https://s3-us-west-2.amazonaws.com/{0}/{1}".format(image_bucket, str(key))
                meta_data = {'FromNumber': from_number, 'url': store_url}
                s3.Bucket(image_bucket).put_object(Key=key, Body=image.read(), ACL='public-read', ContentType='image/png',
                                                   Metadata=meta_data)
                message = store_url

            if user['Previous']:
                user_responses = user['Questions']
                update_response(from_number, len(user_responses)-1, message)
                table_users.update_item(Key={identify_key: from_number, }, UpdateExpression="set Previous = :r",
                                        ExpressionAttributeValues={':r': False}, ReturnValues="UPDATED_NEW")
            else:
                save_response(from_number, message)

    # If the user wants to take the survey, the next question is received
    if has_responded:
        # Checks to see if user wants to go back to previous response
        if previous:
            question = get_previous_question(from_number)
            table_users.update_item(Key={identify_key: from_number, }, UpdateExpression="set Previous = :r",
                                    ExpressionAttributeValues={':r': True}, ReturnValues="UPDATED_NEW")
        else:
            question = get_next_question(from_number)
        response.message(question)

    return str(response)