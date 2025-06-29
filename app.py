from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import Counter
import os # It's good practice to have this for environment variables

app = Flask(__name__)
CORS(app)

def generate_usn_list(prefix, start, end):
    """Generates a list of USNs from a prefix, start, and end number."""
    return [f"{prefix}{i:03}" for i in range(start, end + 1)]

@app.route('/api/generate-allotment', methods=['POST'])
def generate_allotment_api():
    data = request.get_json()

    # --- 1. Extract All Inputs ---
    try:
        room_details = data['roomDetails']
        benches = int(room_details['benches'])
        students_per_bench = int(room_details['studentsPerBench'])
        class_columns = int(room_details['classColumns'])
        
        student_layout_per_bench = [c.strip().upper() for c in data['studentLayout']]
        
        branch_details = data['branchDetails']
        if not branch_details:
            return jsonify({'status': 'error', 'message': 'You must define at least one branch.'}), 400

    except (KeyError, TypeError, ValueError) as e:
        return jsonify({'status': 'error', 'message': f'Invalid or missing input data: {e}'}), 400

    # --- 2. Validation - Phase 1 (Layouts) ---
    if len(student_layout_per_bench) != students_per_bench:
        return jsonify({
            'status': 'error',
            'message': f'Layout Mismatch: The number of student types in your layout ({len(student_layout_per_bench)}) must match students per bench ({students_per_bench}).'
        }), 400

    if class_columns <= 0:
        return jsonify({'status': 'error', 'message': 'Number of class columns must be greater than zero.'}), 400

    # --- Handle Uneven Bench Distribution ---
    base_benches_per_column = benches // class_columns
    remainder_benches = benches % class_columns
    
    benches_in_each_column = [base_benches_per_column] * class_columns
    for i in range(remainder_benches):
        benches_in_each_column[i] += 1
    
    # --- 3. Process Branches and Generate Student Lists ---
    student_lists = {}
    student_counts = {}
    defined_branch_names = set()

    for branch in branch_details:
        try:
            name = branch['name'].strip().upper()
            if not name: continue
            
            prefix = branch['prefix']
            start = int(branch['start'])
            end = int(branch['end'])

            if start > end:
                return jsonify({'status': 'error', 'message': f'For branch {name}, start USN ({start}) cannot be greater than end USN ({end}).'}), 400

            student_lists[name] = generate_usn_list(prefix, start, end)
            student_counts[name] = end - start + 1
            defined_branch_names.add(name)

        except (KeyError, TypeError, ValueError):
            return jsonify({'status': 'error', 'message': f'Invalid data for a branch. Ensure all fields are filled correctly.'}), 400

    # --- 4. Validation - Phase 2 (Layout vs. Students) ---
    layout_branch_counts = Counter(student_layout_per_bench)

    for branch_name_in_layout in layout_branch_counts:
        if branch_name_in_layout not in defined_branch_names:
            return jsonify({'status': 'error', 'message': f'Layout Error: The branch "{branch_name_in_layout}" was used in the layout but was not defined in the branch list.'}), 400
            
        num_students_for_branch = student_counts.get(branch_name_in_layout, 0)
        seats_available_for_branch = layout_branch_counts[branch_name_in_layout] * benches
        
        if num_students_for_branch > seats_available_for_branch:
            return jsonify({
                'status': 'error',
                'message': f'Seat Shortage for {branch_name_in_layout}: This branch requires {num_students_for_branch} seats, but the current layout only provides {seats_available_for_branch} seats across all {benches} benches.'
            }), 400

    # --- 5. Build the Seating Grid (The Core Algorithm) ---
    arrangement_by_column = []
    bench_counter = 1

    for i, benches_for_this_column in enumerate(benches_in_each_column):
        column_seating_plan = []
        for _ in range(benches_for_this_column):
            current_bench_seats = []
            for branch_for_this_seat in student_layout_per_bench:
                if student_lists.get(branch_for_this_seat) and student_lists[branch_for_this_seat]:
                    student = student_lists[branch_for_this_seat].pop(0)
                    current_bench_seats.append(student)
                else:
                    current_bench_seats.append("---")
            
            column_seating_plan.append({
                'bench_number': bench_counter,
                'seats': current_bench_seats
            })
            bench_counter += 1
        
        arrangement_by_column.append({
            'name': f'Column {i + 1} ({benches_for_this_column} Benches)',
            'seating_plan': column_seating_plan
        })

    # --- 6. Send Success Response ---
    return jsonify({
        'status': 'success',
        'student_seat_headers': student_layout_per_bench,
        'arrangement_by_column': arrangement_by_column
    })

# This block is for local development and will NOT be used by Render's Gunicorn server.
if __name__ == '__main__':
    # Render provides the PORT environment variable. Default to 5000 for local use.
    port = int(os.environ.get('PORT', 5000))
    # debug=True is insecure for production. Gunicorn handles this properly.
    app.run(host='0.0.0.0', port=port)
