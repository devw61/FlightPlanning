import pandas as pd
from datetime import datetime, timedelta
import requests
import os
import aiohttp
import asyncio

def get_amadeus_session_token(client_id, client_secret):
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()

async def fetch_flights(session, url, headers, params):
    async with session.get(url, headers=headers, params=params) as response:
        return await response.json()

async def get_flight_offers(token_info):
    from_airport = input("Enter the airport code you are flying from: ")
    to_airport = input("Enter the airport code you are flying to: ")
    date = input("Enter the date you are flying (YYYY-MM-DD): ")
    adults = int(input("Enter the number of adults flying: "))

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token_info}"}
    params = {
        "originLocationCode": from_airport,
        "destinationLocationCode": to_airport,
        "departureDate": date,
        "adults": adults,
        "currencyCode": "USD"
    }

    print("Fetching flight data...")
    async with aiohttp.ClientSession() as session:
        return await fetch_flights(session, url, headers, params)
    

async def fetch_pricing(session, url, headers, flight, delay):
    await asyncio.sleep(delay)  # Add delay to avoid rate limit
    async with session.post(url, headers=headers, json={"data": {"type": "flight-offers-pricing", "flightOffers": [flight]}}) as response:
        return await response.json()

async def get_pricing_responses(token_info, flights):
    url = "https://test.api.amadeus.com/v1/shopping/flight-offers/pricing?forceClass=false"
    headers = {"Authorization": f"Bearer {token_info}"}
    print("Fetching pricing data...")
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_pricing(session, url, headers, flight, i * 1) for i, flight in enumerate(flights) if i < 10]  # only do the first 10, rest 
        return await asyncio.gather(*tasks)
    
def format_flight_data(flight_data):
    for flight_plan in flight_data:
        abbr_plan = f"{flight_plan['itinerary'][0]['segments'][0]['departure']['iataCode']}"
        segments = flight_plan['itinerary'][0]['segments']
        for i in range(len(segments) - 1):

            # calc layover duration
            arrival_code = segments[i]['arrival']['iataCode']
            next_departure_time = datetime.fromisoformat(segments[i + 1]['departure']['at'])
            arrival_time = datetime.fromisoformat(segments[i]['arrival']['at'])
            layover_duration = next_departure_time - arrival_time
            hours, remainder = divmod(layover_duration.total_seconds(), 3600)
            minutes = remainder // 60
            layover_str = f" (layover: {int(hours)}h {int(minutes)}m)"
            abbr_plan += f" -> {arrival_code}{layover_str}"

        abbr_plan += f" -> {segments[-1]['arrival']['iataCode']}"
    
        flight_plan['flight_plan'] = abbr_plan
        flight_plan['carrierCode'] = segments[0]['carrierCode']
        
        # calculate total duration
        departure_time = datetime.fromisoformat(segments[0]['departure']['at'])
        arrival_time = datetime.fromisoformat(segments[-1]['arrival']['at'])
        total_duration = arrival_time - departure_time
        hours, remainder = divmod(total_duration.total_seconds(), 3600)
        minutes = remainder // 60
        flight_plan['trip_total_duration'] = pd.to_timedelta(f"{int(hours)}:{int(minutes)}:00")
        flight_plan.pop('itinerary')

    return pd.DataFrame(flight_data)

# get price data
client_id = os.environ['AMADEUS_API_KEY']
client_secret = os.environ['AMADEUS_SECRET']
token_info = get_amadeus_session_token(client_id, client_secret)['access_token']

flights_response = asyncio.run(get_flight_offers(token_info))
if flights_response['data'] == []:
    print("No flights found for the given criteria.")
    exit()

pricing_responses = asyncio.run(get_pricing_responses(token_info, flights_response['data']))

pricing_flight_data = []
for jsonified in pricing_responses:
    if 'errors' not in jsonified:
        pricing_flight_data.append({'itinerary': jsonified['data']['flightOffers'][0]['itineraries'],
                        'price': jsonified['data']['flightOffers'][0]['price']['grandTotal']})
        
flight_pricing_df = format_flight_data(pricing_flight_data)

flight_pricing_df['price'] = flight_pricing_df['price'].astype(float)
if input("Would you like to sort by price or duration? (p/d): ") == 'p':
    sorted_flight_pricing_df = flight_pricing_df.sort_values(by=['price', 'trip_total_duration'])
else :
    sorted_flight_pricing_df = flight_pricing_df.sort_values(by=['trip_total_duration', 'price'])

print(sorted_flight_pricing_df.head(10).to_string(index=False))

print("\033[92m\nUse https://www.iata.org/en/publications/directories/code-search/ to find carrier codes.\033[0m")
