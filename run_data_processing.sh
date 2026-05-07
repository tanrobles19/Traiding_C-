#!/bin/bash

# Activate the virtual environment (make sure it's activated first)
echo "Activating the virtual environment..."
source myenv/bin/activate

# Clear all tables
# python3 clean_db.py

# Run the Python scripts
python3 fetch_historycal_data_to_db.py

python3 get_float.py

python3 get_previous_close.py

python3 relative_volume_ratio.py

echo "Process completed."