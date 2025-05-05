import os
import requests
import time

output_dir = "valid_postings"
os.makedirs(output_dir, exist_ok=True)

base_url = "https://studentjobs.library.utoronto.ca/index.php/posting/view/{}"
current_max = 3710 # Should be updated with latest served posting on site
# prev_max # The last posting ID from the previous run that was successfully saved

# Loop over suspected potential posting IDs
for posting_id in range(3696, current_max + 1):
    url = base_url.format(posting_id)
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as e:
        print(f"Error fetching posting {posting_id}: {e}")
        continue

    if response.status_code != 200:
        print(f"Posting {posting_id} returned status code {response.status_code}")
        continue

    html_content = response.text

    if "Invalid posting ID" in html_content:
        print(f"Posting {posting_id} is invalid, skipping.")
        continue

    file_path = os.path.join(output_dir, f"posting_{posting_id}.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Saved posting {posting_id} successfully.")

    time.sleep(2)
