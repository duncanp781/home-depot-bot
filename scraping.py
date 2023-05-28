import re
import json
import random
import requests
from bs4 import BeautifulSoup
from langchain.agents import tool


# Takes a plain-text query, like 'grills'.
# Query-type can be a few different things. 'b' for categories, 'p' for pages
def get_links(query, query_type='b'):
    url = f'https://homedepot.com/s/{query}?NCNI-5'

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0'}
    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(response.text, features='lxml')
    links = soup.find_all('a', href=True)

    # The links in the anchors are relative, so start with /
    query_regex = r'^/' + re.escape(query_type) + r'/.*'
    cat_links = [
        f'https://homedepot.com{link["href"]}' for link in links if re.match(query_regex, link['href'])]
    return cat_links


@tool
def get_homedepot_pages(query):
    """Use this to find the url for products on the home depot website.
    You should ask for the names of products.
    Be specific: 'propane grill' gives better results than 'grill'
    It will return a sentence telling you a product and its url.
    If the output does not seem appropriate for the query, ask the same query again.
    """
    page_links = get_links(query, 'p')
    pages_split = [[link] + link.split('/')[3:] for link in page_links]
    selected_page_index = random.randrange(len(pages_split))
    page = pages_split[selected_page_index]

    page_dict = {'link': page[0], 'page-type': page[1],
                 'name': page[2].replace('-', ' ')}
    page_string = f'A product with name {page_dict["name"]} is available at the url {page_dict["link"]}. '
    return page_string


def get_name(page):
    product_details = page.find("div", class_="product-details")
    if product_details:
        name = product_details.find('h1')
        if name:
            return name.text.strip()
    return "Name not found"


def get_company(page):
    product_details = page.find("div", class_="product-details")
    if product_details:
        company = product_details.find('h2')
        if company:
            return company.text.strip()
    return "Company not found"

# This is to add periods to prices for products, since they are missing from the html.

def add_period(text):
    digits = ''.join([char for char in text if char.isdigit()])
    fixed_digits = digits[:-2] + '.' + digits[-2:]
    return text.replace(digits, fixed_digits)


def get_price(page):
    price = page.select_one('div[class^="price"]')
    if price and len(price.text.strip()) > 1:
        price_text = "Price: " + price.text.strip()
        if len(price_text) > 2:
            return add_period(price_text)
    else:
        return "Price information not found"


def get_details(page):
    desc = page.find('ul', class_='sui-list-disc')
    if desc:
        desc_text = "Item Description:"
        for li in desc.find_all('li')[:-1]:
            desc_text += ' ' + li.text
        return desc_text
    else:
        return "Description not found"
        

def get_reviews(page):
  star_span = page.select_one('span[class="stars--c43xm"]')
  stars = None
  review_count = None
  if star_span: 
    style = star_span.get('style')
    print(style)
    match = re.search(r'\d+\.?\d+', style)
    print(match)
    if match:
      width = float(match.group())
      stars =  str(round(width/20, 1))
  review_span = page.select_one('span[class="product-details__review-count"]')
  if review_span:
    review_count = ''.join([char for char in review_span.text if char.isdigit()])
    print(review_count)
  if stars and review_count:
    return f"The product gets {stars} stars over {review_count} reviews"
  else:
    return "Could not find review information"

def test_getter(getter):
  url = "https://homedepot.com/p/Trexonic-Portable-Screen-Size-Class-14-in-Rechargeable-LED-HDTV-985110646M/310955410"
  headers = {
        "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
  response = requests.get(url, headers=headers)
  soup = BeautifulSoup(response.text, features='lxml')

  print(getter(soup))

@tool
def get_homedepot_page_info(url):
    """Use this to get information about the product located at this url.
    The url passed in must look like https://homedepot.com/p/...,
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, features='lxml')

    name_text = get_name(soup)
    company_text = get_company(soup)
    desc_text = get_details(soup)
    price_text = get_price(soup)
    review_text = get_reviews(soup)

    out = f"At url {url} is the item named {name_text} from company {company_text}. {desc_text}. {price_text}. {review_text}."
    return out

scraping_tools = [get_homedepot_pages, get_homedepot_page_info]

test_getter(get_reviews)