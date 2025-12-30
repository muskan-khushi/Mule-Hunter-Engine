import pandas as pd
import os
import logging

# Path to where you will put the Kaggle CSVs
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared-data")

def generate_dataset():
    print(f"🚀 Initializing Kaggle-to-Graph Migration...")
    
    # 1. PATH CHECK - Assume the Kaggle files are in shared-data
    train_trans_path = os.path.join(OUTPUT_DIR, "train_transaction.csv")
    train_id_path = os.path.join(OUTPUT_DIR, "train_identity.csv")

    if not os.path.exists(train_trans_path):
        print(f"❌ ERROR: train_transaction.csv not found in {OUTPUT_DIR}")
        return

    # 2. LOAD & MERGE (Sampling 50k rows so your laptop stays fast)
    print("📥 Loading and Merging Kaggle Files...")
    df_trans = pd.read_csv(train_trans_path, nrows=50000)
    df_id = pd.read_csv(train_id_path)
    
    # Merge on TransactionID
    df = pd.merge(df_trans, df_id, on='TransactionID', how='left')
    
    # 3. MAP TO YOUR EXISTING SCHEMA (The "Bridge")
    # We use 'card1' as the User ID (The Node)
    # We use 'D1' as the Account Age
    # We use 'TransactionAmt' as the Balance
    
    print("🛠️ Mapping Kaggle columns to Mule Hunter schema...")
    df_nodes = pd.DataFrame()
    df_nodes['node_id'] = df['card1'].astype(str)
    df_nodes['account_age_days'] = df['D1'].fillna(0).astype(int)
    df_nodes['balance'] = df['TransactionAmt'].fillna(0)
    df_nodes['is_fraud'] = df['isFraud']
    
    # Placeholders to keep feature_engineering.py happy
    df_nodes['pagerank'] = 0.0001
    df_nodes['in_out_ratio'] = 1.0
    df_nodes['tx_velocity'] = 1
    
    # Remove duplicates so each card/user is only listed once in nodes.csv
    df_nodes = df_nodes.drop_duplicates(subset=['node_id'])
    
    # Save nodes.csv
    df_nodes.to_csv(os.path.join(OUTPUT_DIR, "nodes.csv"), index=False)
    print(f"✅ Saved nodes.csv ({len(df_nodes)} unique cards/users)")

    # 4. CREATE TRANSACTIONS (The Edges)
    # We create a link between a User (card1) and a Merchant/Location (addr1)
    df_edges = pd.DataFrame()
    df_edges['source'] = df['card1'].astype(str)
    df_edges['target'] = df['addr1'].fillna(0).astype(int).astype(str)
    df_edges['amount'] = df['TransactionAmt']
    df_edges['timestamp'] = df['TransactionDT'] # Kaggle time offset

    # Save transactions.csv
    df_edges.to_csv(os.path.join(OUTPUT_DIR, "transactions.csv"), index=False)
    print(f"✅ Saved transactions.csv ({len(df_edges)} money flows)")
    print("🚀 MIGRATION COMPLETE: System is now running on real Kaggle data.")

if __name__ == "__main__":
    generate_dataset()