from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
from selenium.common.exceptions import NoSuchElementException

def perform_google_search(search_query):
    # Setup the Chrome driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    try:
        # Open Google
        driver.get("https://www.google.com")

        # Handle cookies popup
        try:
            agree_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree') or contains(text(), 'Accept all')]"))
            )
            agree_button.click()
        except:
            pass

        # Locate the search box and submit the query
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        search_box.send_keys(search_query)
        search_box.send_keys(Keys.RETURN)

        # Wait for results to load
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.ID, "search"))
        )

        # Initialize results dictionary
        results_data = {
            "top_results": [],
            "featured_snippet": "",
            "people_also_ask": [],
            "video_links": [],
            "top_ads_count": 0,
            "bottom_ads_count": 0,
            "ai_overview": "",
            "image_links": [],
            "site_links": [],
            "local_businesses": []
        }

        # Fetch top search results
        results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
        for idx, result in enumerate(results):
            title, url = "", ""
            try:
                title = result.find_element(By.XPATH, ".//h3").text
                url = result.find_element(By.XPATH, ".//a").get_attribute("href")
                if title and url:
                    results_data["top_results"].append({"title": title, "url": url})
            except:
                continue

        # Fetch Featured Snippet
        try:
            featured_snippet = driver.find_element(By.XPATH, "//div[contains(@class, 'VNzqVe')]")
            results_data["featured_snippet"] = featured_snippet.text
        except:
            results_data["featured_snippet"] = "No featured snippet found."

        # Fetch People Also Ask
        people_also_ask = driver.find_elements(By.CSS_SELECTOR, '.related-question-pair')
        results_data["people_also_ask"] = [question.text for question in people_also_ask]

        # Fetch Video Links
        video_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="youtube.com"]')
        results_data["video_links"] = [video.get_attribute('href') for video in video_links]

        # Count Top and Bottom Ads
        top_ads = driver.find_elements(By.CSS_SELECTOR, "div[data-hveid='CAQQAQ']")
        results_data["top_ads_count"] = len(top_ads)
        bottom_ads = driver.find_elements(By.CSS_SELECTOR, "div[data-hveid='CAQQAQ']")
        results_data["bottom_ads_count"] = len(bottom_ads)

        # Fetch AI Overview
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CLASS_NAME, "WaaZC"))
            )
            ai_overview = driver.find_element(By.CLASS_NAME, "WaaZC")
            results_data["ai_overview"] = ai_overview.text
        except:
            results_data["ai_overview"] = "No AI Overview Section found."

        # Fetch Image Links
        image_links = driver.find_elements(By.CSS_SELECTOR, 'img')
        results_data["image_links"] = [img.get_attribute('src') for img in image_links if img.get_attribute('src')]

        # Fetch Site Links
        site_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="https://"]')
        results_data["site_links"] = [link.get_attribute('href') for link in site_links]

        # Fetch the top businesses in the local pack
        businesses = []

        # Get the business containers using the VkpGBb class
        business_containers = driver.find_elements(By.CSS_SELECTOR, 'div.VkpGBb')

        # Iterate over the business containers and extract the details
        for idx, business in enumerate(business_containers):
            business_data = {}

            # Extract the business name
            try:
                name = business.find_element(By.CSS_SELECTOR, 'span.OSrXXb').text.strip()
                business_data['name'] = name
            except NoSuchElementException:
                business_data['name'] = "Name not found"

            # Extract the rating and review count
            try:
                rating = business.find_element(By.CSS_SELECTOR, '.yi40Hd').text.strip()
                review_count = business.find_element(By.CSS_SELECTOR, '.RDApEe').text.strip()
                business_data['rating'] = rating
                business_data['review_count'] = review_count
            except NoSuchElementException:
                business_data['rating'] = "Rating not found"
                business_data['review_count'] = "Review count not found"

            # Extract the address
            try:
                address = business.find_element(By.CSS_SELECTOR, '.rllt__details span').text.strip()
                business_data['address'] = address
            except NoSuchElementException:
                business_data['address'] = "Address not found"

            # Extract the description
            try:
                description = business.find_element(By.CSS_SELECTOR, '.uDyWh').text.strip()
                business_data['description'] = description
            except NoSuchElementException:
                business_data['description'] = "Description not found"

            # Add the business data to the list
            businesses.append(business_data)

        results_data["local_businesses"] = businesses

        return results_data
    finally:
        driver.quit()