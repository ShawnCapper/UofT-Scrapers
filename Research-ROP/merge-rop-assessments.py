import json

def merge_course_assessments_with_sessions(courses_file, assessments_file, output_file):
    """
    Merges assessment data from assessments.json into courses.json based on course titles and sessions.

    Args:
        courses_file (str): Path to the courses.json file.
        assessments_file (str): Path to the assessments.json file.
        output_file (str): Path to the output file to save the merged data.
    """

    with open(courses_file, 'r') as f:
        courses_data = json.load(f)

    with open(assessments_file, 'r') as f:
        assessments_data = json.load(f)

    assessment_lookup = {}
    for assessment_item in assessments_data:
        assessment_title = assessment_item['course']['title']
        assessment_session = assessment_item['course']['session']
        assessment_matrix = assessment_item['assessment_matrix']

        if assessment_title not in assessment_lookup:
            assessment_lookup[assessment_title] = []  # Initialize as a list if title not seen yet

        assessment_lookup[assessment_title].append({
            'session': assessment_session,
            'assessment_matrix': assessment_matrix
        })

    updated_courses_data = []
    for course in courses_data:
        course_title = course['Title']
        if course_title in assessment_lookup:
            course['Assessment Matrix'] = assessment_lookup[course_title]
        else:
            course['Assessment Matrix'] = []  # Add empty list if no assessment found
        updated_courses_data.append(course)

    with open(output_file, 'w') as f:
        json.dump(updated_courses_data, f, indent=2)

if __name__ == "__main__":
    courses_file = '../UofT-Scrapers/courses.json'
    assessments_file = '../UofT-Scrapers/assessments.json'
    output_file = '../UofT-Scrapers/courses_updated_with_sessions.json'

    merge_course_assessments_with_sessions(courses_file, assessments_file, output_file)
    print(f"Merged data with session-specific assessments saved to {output_file}")