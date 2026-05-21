import sqlite3
import os
import sys

# Add src to path to import BacklogManager
sys.path.append(os.path.join(os.getcwd(), 'src'))
from tools.backlog_manager import BacklogManager

conn = sqlite3.connect('.exegol/backlog.db')
cursor = conn.cursor()
cursor.execute('''DELETE FROM tasks WHERE id IN (
    "arch_cross_repo_handoffs", 
    "arch_federated_backlog", 
    "arch_phase4_cross_repo_impl"
)''')
conn.commit()
conn.close()

bm = BacklogManager('.')
bm._sync_to_json()
print("Done!")
