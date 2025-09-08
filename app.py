# app.py

from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import defaultdict

app = Flask(__name__)
CORS(app)

@app.route('/api/generate-allotment', methods=['POST'])
def generate_allotment_api():
    """
    Final, most advanced API.
    - Automates layout creation based on a single 'studentsPerBench' number.
    - Uses the (A, B, A, B...) pattern for separation.
    - Implements "sticky pairing" to ensure columnar consistency.
    - Handles "Common Paper Groups" by merging them first.
    - Gracefully handles a single branch input.
    - Supports a specific per-column bench distribution via 'benchesInColumns'.
    - MODIFIED: Processes a combined list of student USNs and their subject codes, allowing for manual and file inputs.
    - MODIFIED: Groups students by subject code for seating, not by branch/USN prefix.
    """
    data = request.get_json()

    try:
        room_configurations = data['roomConfigurations']
        students_per_bench = int(data['studentsPerBench'])
        common_groups_str = data.get('commonPaperGroups', '')
        combined_student_data = data.get('combinedStudentData', [])
        skipped_students_report = data.get('skippedStudentsReport', {})

        if not combined_student_data:
            return jsonify({'status': 'error', 'message': 'No student data provided. Please upload a file or add manual entries.'}), 400
        if not room_configurations:
            return jsonify({'status': 'error', 'message': 'You must define at least one room.'}), 400
        if students_per_bench <= 0:
            return jsonify({'status': 'error', 'message': 'Students per bench must be greater than 0.'}), 400

    except (KeyError, TypeError, ValueError) as e:
        return jsonify({'status': 'error', 'message': f'Invalid or missing root input data: {e}'}), 400

    # Group students by subject code
    initial_student_lists = defaultdict(list)
    for student in combined_student_data:
        usn = student['usn'].strip().upper()
        subject_code = student['subjectCode'].strip().upper()
        initial_student_lists[subject_code].append(usn)

    # Apply common paper grouping
    final_student_lists = defaultdict(list)
    processed_in_group = set()
    common_groups = [g for g in parse_common_groups(common_groups_str) if len(g) > 1] # Only process groups with more than one item

    for group in common_groups:
        group_name = ', '.join(sorted(group)) # Use a consistent name for the merged group
        merged_list = []
        for subject_code in group:
            if subject_code in initial_student_lists:
                merged_list.extend(initial_student_lists[subject_code])
                processed_in_group.add(subject_code)
        if merged_list:
            final_student_lists[group_name] = merged_list

    for subject_code, students in initial_student_lists.items():
        if subject_code not in processed_in_group:
            final_student_lists[subject_code] = students
    
    # Sort all student lists to ensure a consistent seating order
    for subject_code in final_student_lists:
        final_student_lists[subject_code].sort()
    
    total_benches = sum(int(room['benches']) for room in room_configurations)
    
    # --- "STICKY PAIRING" SEATING LOGIC (UNCHANGED) ---
    seated_benches = []
    working_student_lists = {k: list(v) for k, v in final_student_lists.items()}
    
    while sum(len(v) for v in working_student_lists.values()) > 0 and len(seated_benches) < total_benches:
        available_groups = sorted([name for name, students in working_student_lists.items() if students], key=lambda name: len(working_student_lists[name]), reverse=True)
        if not available_groups:
            break
        
        primary_group_name = available_groups[0]
        secondary_group_name = available_groups[1] if len(available_groups) > 1 else None
        
        primary_list = working_student_lists[primary_group_name]
        secondary_list = working_student_lists.get(secondary_group_name)

        while primary_list and (secondary_group_name is None or secondary_list):
            if len(seated_benches) >= total_benches:
                break
            
            current_bench_seats = []
            seating_pattern = [primary_group_name if i % 2 == 0 else secondary_group_name for i in range(students_per_bench)]
            
            for group_name in seating_pattern:
                if group_name and group_name in working_student_lists and working_student_lists[group_name]:
                    current_bench_seats.append(working_student_lists[group_name].pop(0))
                else:
                    current_bench_seats.append("---")
            seated_benches.append(current_bench_seats)
    # --- SEATING LOGIC ENDS ---

    room_arrangements = []
    seated_bench_index = 0

    for room_config in room_configurations:
        bench_counter = 1
        if seated_bench_index >= len(seated_benches):
            break
        
        try:
            room_name = room_config.get('name', f"Room {len(room_arrangements) + 1}")
            benches = int(room_config['benches'])
            class_columns = int(room_config['classColumns'])
            if benches <= 0 or class_columns <= 0:
                return jsonify({'status': 'error', 'message': f'Benches and columns must be positive for room {room_name}.'}), 400
        except (ValueError, KeyError) as e:
            return jsonify({'status': 'error', 'message': f'Invalid benches or column data for a room: {e}'}), 400

        benches_in_each_column = []
        if 'benchesInColumns' in room_config and room_config['benchesInColumns']:
            try:
                benches_in_each_column = [int(b) for b in room_config['benchesInColumns']]
                if sum(benches_in_each_column) != benches:
                    return jsonify({'status': 'error', 'message': f'For room {room_name}, sum of column benches ({sum(benches_in_each_column)}) != total benches ({benches}).'}), 400
                if len(benches_in_each_column) != class_columns:
                    return jsonify({'status': 'error', 'message': f'For room {room_name}, # of column distributions ({len(benches_in_each_column)}) != # of columns ({class_columns}).'}), 400
            except (ValueError, TypeError):
                 return jsonify({'status': 'error', 'message': f'Invalid data in benchesInColumns for room {room_name}.'}), 400
        else:
            benches_in_each_column = [benches // class_columns + (1 if i < benches % class_columns else 0) for i in range(class_columns)]
        
        arrangement_by_column = []
        for i, benches_for_this_column in enumerate(benches_in_each_column):
            if seated_bench_index >= len(seated_benches):
                break
            column_seating_plan = []
            for _ in range(benches_for_this_column):
                if seated_bench_index >= len(seated_benches):
                    break
                column_seating_plan.append({'bench_number': bench_counter, 'seats': seated_benches[seated_bench_index]})
                seated_bench_index += 1
                bench_counter += 1
            if column_seating_plan:
                arrangement_by_column.append({'name': f'Column {i + 1} ({len(column_seating_plan)} Benches)', 'seating_plan': column_seating_plan})
        
        if arrangement_by_column:
            room_arrangements.append({"room_name": room_name, "arrangement_by_column": arrangement_by_column})

    unseated_students = {subject: sorted(students) for subject, students in working_student_lists.items() if students}
    seat_headers = [f'Seat {i+1}' for i in range(students_per_bench)]

    return jsonify({
        'status': 'success',
        'student_seat_headers': seat_headers,
        'room_arrangements': room_arrangements,
        'skipped_students': skipped_students_report,
        'unseated_students': unseated_students,
        'group_map': initial_student_lists # Send this back for PDF generation logic
    })

def parse_common_groups(group_str):
    groups = []
    if not group_str:
        return groups
    pairs = [p.strip() for p in group_str.upper().split(';') if p.strip()]
    for pair in pairs:
        branches = [b.strip() for b in pair.split(',') if b.strip()]
        if branches:
            groups.append(branches)
    return groups

if __name__ == '__main__':
    # MODIFIED LINE: Added host='0.0.0.0'
    app.run(host='0.0.0.0', debug=True, port=5000)
