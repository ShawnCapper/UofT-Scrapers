""" Generate job statistics based on parsed data. """

import json
import argparse
from collections import Counter, defaultdict
from datetime import datetime


def load_data(json_file):
    """Load and return data from the specified JSON file."""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def parse_salary(salary_list):
    """Convert salary values to float."""
    cleaned_salaries = []
    for salary in salary_list:
        try:
            # If already numeric, use directly
            if isinstance(salary, (int, float)):
                cleaned_salaries.append(float(salary))
            else:
                # If string with dollar sign, convert
                cleaned_salary = float(str(salary).replace('$', '').strip())
                cleaned_salaries.append(cleaned_salary)
        except (ValueError, AttributeError):
            continue
    return cleaned_salaries


def calculate_average(numbers):
    """Calculate the average of a list of numbers."""
    if not numbers:
        return 0
    return sum(numbers) / len(numbers)


def calculate_median(numbers):
    """Calculate the median of a list of numbers."""
    if not numbers:
        return 0
    sorted_numbers = sorted(numbers)
    length = len(sorted_numbers)
    mid = length // 2

    if length % 2 == 0:
        # If even number of elements, average the two middle values
        return (sorted_numbers[mid - 1] + sorted_numbers[mid]) / 2
    else:
        # If odd number of elements, return the middle value
        return sorted_numbers[mid]


def generate_statistics(data):
    """Generate comprehensive statistics from the loaded data."""
    stats_data = {
        'total_postings': len(data),
        'departments': Counter(),
        'positions': Counter(),
        'salary_stats': {
            'min': float('inf'),
            'max': float('-inf'),
            'avg': 0,
            'median': 0
        },
        'html_folder_counts': Counter(),
        'postings_by_month': Counter(),
        'periods_of_employment': Counter(),
        'hours_stats': {'min': float('inf'), 'max': float('-inf'), 'avg': 0, 'median': 0},
        'accepted_until_by_month': Counter()
    }

    all_salaries = []
    hours_list = []

    for entry in data:
        # Department statistics
        dept = entry.get('department', 'Unknown')
        stats_data['departments'][dept] += 1

        # Position statistics
        position = entry.get('position', 'Unknown')
        stats_data['positions'][position] += 1

        # Salary statistics
        if 'hourly_rate' in entry and isinstance(entry['hourly_rate'], list):
            salaries = parse_salary(entry['hourly_rate'])
            all_salaries.extend(salaries)

        # HTML folder statistics
        folder = entry.get('html_folder', 'Unknown')
        stats_data['html_folder_counts'][folder] += 1

        # Timestamp/date statistics
        if 'timestamp' in entry:
            try:
                date = datetime.fromisoformat(entry['timestamp'])
                month_year = date.strftime('%Y-%m')
                stats_data['postings_by_month'][month_year] += 1
            except (ValueError, TypeError):
                stats_data['postings_by_month']['Unknown'] += 1

        # Period of Employment statistics
        period = entry.get('period_of_employment', 'Unknown')
        stats_data['periods_of_employment'][period] += 1

        # Hours per week statistics
        if 'hours_per_week' in entry:
            import re
            matches = re.findall(r'\d+\.\d+|\d+', str(entry['hours_per_week']))
            for m in matches:
                hours_list.append(float(m))

        # Accepted until deadlines by month
        if 'accepted_until' in entry:
            try:
                dt = datetime.fromisoformat(entry['accepted_until'])
            except (ValueError, TypeError):
                try:
                    dt = datetime.strptime(entry['accepted_until'], '%B %d, %Y')
                except (ValueError, TypeError):
                    stats_data['accepted_until_by_month']['Unknown'] += 1
                else:
                    stats_data['accepted_until_by_month'][dt.strftime('%Y-%m')] += 1
            else:
                stats_data['accepted_until_by_month'][dt.strftime('%Y-%m')] += 1

    # Calculate salary statistics if we have salary data
    if all_salaries:
        stats_data['salary_stats']['min'] = min(all_salaries)
        stats_data['salary_stats']['max'] = max(all_salaries)
        stats_data['salary_stats']['avg'] = calculate_average(all_salaries)
        stats_data['salary_stats']['median'] = calculate_median(all_salaries)

    # Calculate hours per week statistics if we have hours data
    if hours_list:
        stats_data['hours_stats']['min'] = min(hours_list)
        stats_data['hours_stats']['max'] = max(hours_list)
        stats_data['hours_stats']['avg'] = calculate_average(hours_list)
        stats_data['hours_stats']['median'] = calculate_median(hours_list)

    return stats_data


def print_statistics(stats_data):
    """Print the statistics in a formatted way."""
    print("\n=== Job Posting Statistics ===\n")

    print(f"Total number of postings: {stats_data['total_postings']}")

    print("\n=== Department Statistics ===")
    for dept, count in sorted(stats_data['departments'].items(), key=lambda x: x[1], reverse=True):
        print(f"{dept}: {count} postings")

    print("\n=== Top 10 Positions ===")
    for pos, count in sorted(stats_data['positions'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{pos}: {count} postings")

    print("\n=== Period of Employment Distribution ===")
    for period, count in sorted(stats_data['periods_of_employment'].items(), key=lambda x: x[1], reverse=True):
        print(f"{period}: {count} postings")

    print("\n=== Hours Per Week Statistics ===")
    if stats_data['hours_stats']['min'] != float('inf'):
        print(f"Minimum hours per week: {stats_data['hours_stats']['min']:.2f}")
        print(f"Maximum hours per week: {stats_data['hours_stats']['max']:.2f}")
        print(f"Average hours per week: {stats_data['hours_stats']['avg']:.2f}")
        print(f"Median hours per week: {stats_data['hours_stats']['median']:.2f}")

    print("\n=== Salary Statistics ===")
    if stats_data['salary_stats']['min'] != float('inf'):
        print(f"Minimum hourly rate: ${stats_data['salary_stats']['min']:.2f}")
        print(f"Maximum hourly rate: ${stats_data['salary_stats']['max']:.2f}")
        print(f"Average hourly rate: ${stats_data['salary_stats']['avg']:.2f}")
        print(f"Median hourly rate: ${stats_data['salary_stats']['median']:.2f}")

    print("\n=== Postings by Month ===")
    for month, count in sorted(stats_data['postings_by_month'].items()):
        print(f"{month}: {count} postings")

    print("\n=== HTML Folder Distribution ===")
    for folder, count in sorted(stats_data['html_folder_counts'].items()):
        print(f"{folder}: {count} postings")

    print("\n=== Accepted Until Deadlines by Month ===")
    for month, count in sorted(stats_data['accepted_until_by_month'].items()):
        print(f"{month}: {count} postings")


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive statistics from parsed job posting data"
    )
    parser.add_argument(
        "json_file",
        nargs="?",
        default="archive.json",
        help="Path to the JSON file containing job posting data (default: archive.json)"
    )
    args = parser.parse_args()

    try:
        data = load_data(args.json_file)
        stats_data = generate_statistics(data)
        print_statistics(stats_data)
    except FileNotFoundError:
        print(f"Error: Could not find the file '{args.json_file}'")
    except json.JSONDecodeError:
        print(f"Error: '{args.json_file}' is not a valid JSON file")
    except Exception as e:
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
