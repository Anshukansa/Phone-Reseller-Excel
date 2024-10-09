import os
import dropbox
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from flask import Flask
import io

# Initialize Flask App
app = Flask(__name__)

# Allowed Users (Telegram User IDs)
ALLOWED_USERS = [123456789, 987654321]  # Add allowed user IDs here

# Conversation states
CHOOSE_ACTION, ADD_BUY, ADD_SELL, CHOOSE_PRODUCT, SELL_DETAILS = range(5)

# Dropbox Client
dbx = dropbox.Dropbox(os.getenv('DROPBOX_ACCESS_TOKEN'))

# Function to download Excel from Dropbox
def download_excel():
    _, res = dbx.files_download('/path/to/excel/Phone Management.xlsx')  # Replace with your file path
    return io.BytesIO(res.content)

# Function to upload the modified Excel back to Dropbox
def upload_excel(file_content):
    dbx.files_upload(file_content.getvalue(), '/path/to/excel/Phone Management.xlsx', mode=dropbox.files.WriteMode.overwrite)

# Function to check if user is allowed
def allowed_user(func):
    def wrapper(update: Update, context):
        user_id = update.message.from_user.id
        if user_id not in ALLOWED_USERS:
            update.message.reply_text("You are not allowed to use this bot.")
            return ConversationHandler.END
        return func(update, context)
    return wrapper

# Start conversation
@allowed_user
def start(update: Update, context):
    reply_keyboard = [['1: Add Buy Entry', '2: Add Sell Entry']]
    update.message.reply_text(
        "Welcome! Choose an option by typing the number:\n1: Add Buy Entry\n2: Add Sell Entry",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CHOOSE_ACTION

# Handle chosen action (Buy or Sell)
@allowed_user
def choose_action(update: Update, context):
    action = update.message.text
    if action.startswith('1'):
        update.message.reply_text("Please provide the details in this format:\nSerial Number, Model, Storage, Purchase Price, Purchase Date")
        return ADD_BUY
    elif action.startswith('2'):
        # Fetch unsold products
        excel_file = download_excel()
        df = pd.read_excel(excel_file)
        unsold_products = df[df['Sell Date'].isna() & df['Sell Price'].isna()]
        
        if unsold_products.empty:
            update.message.reply_text("There are no unsold products.")
            return ConversationHandler.END
        
        products_list = "\n".join([f"{row.Index}: {row.Model} - {row['Serial Number']}" for row in unsold_products.itertuples()])
        context.user_data['unsold_products'] = unsold_products
        update.message.reply_text(f"Choose a product to sell by number:\n{products_list}")
        return CHOOSE_PRODUCT

# Handle buy entry
@allowed_user
def add_buy_entry(update: Update, context):
    try:
        # Get user input
        data = update.message.text.split(',')
        if len(data) != 5:
            raise ValueError("Incorrect format. Provide 5 values separated by commas.")

        # Download Excel
        excel_file = download_excel()
        df = pd.read_excel(excel_file)

        # Append new row
        new_entry = {
            'Index': len(df) + 1,
            'Serial Number': data[0].strip(),
            'Model': data[1].strip(),
            'Storage': data[2].strip(),
            'Purchase Price': data[3].strip(),
            'Sell Price': None,
            'Purchase Date': data[4].strip(),
            'Sell Date': None
        }
        df = df.append(new_entry, ignore_index=True)

        # Save and upload the Excel file
        excel_output = io.BytesIO()
        df.to_excel(excel_output, index=False)
        upload_excel(excel_output)

        # Send confirmation message with full details
        update.message.reply_text(
            f"Buy entry added successfully! Here are the details:\n\n"
            f"Serial Number: {new_entry['Serial Number']}\n"
            f"Model: {new_entry['Model']}\n"
            f"Storage: {new_entry['Storage']}\n"
            f"Purchase Price: {new_entry['Purchase Price']}\n"
f"Purchase Date: {new_entry['Purchase Date']}\n"
        )
    except Exception as e:
        update.message.reply_text(f"Error: {e}")
    
    return ConversationHandler.END

# Handle product selection for sell
@allowed_user
def choose_product(update: Update, context):
    try:
        product_index = int(update.message.text)
        unsold_products = context.user_data['unsold_products']
        
        if product_index not in unsold_products.index:
            raise ValueError("Invalid product number.")

        context.user_data['selected_product'] = product_index
        update.message.reply_text("Provide the Sell Date and Sell Price (format: YYYY-MM-DD, Price):")
        return SELL_DETAILS
    except Exception as e:
        update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

# Handle sell entry
@allowed_user
def add_sell_entry(update: Update, context):
    try:
        # Get user input
        data = update.message.text.split(',')
        if len(data) != 2:
            raise ValueError("Incorrect format. Provide 2 values separated by a comma.")

        sell_date = data[0].strip()
        sell_price = data[1].strip()

        # Download Excel
        excel_file = download_excel()
        df = pd.read_excel(excel_file)

        # Update the selected product
        product_index = context.user_data['selected_product']
        df.at[product_index, 'Sell Date'] = sell_date
        df.at[product_index, 'Sell Price'] = sell_price

        # Save and upload the Excel file
        excel_output = io.BytesIO()
        df.to_excel(excel_output, index=False)
        upload_excel(excel_output)

        # Send confirmation message with full details
        selected_product = df.loc[product_index]
        update.message.reply_text(
            f"Sell entry updated successfully! Here are the details:\n\n"
            f"Serial Number: {selected_product['Serial Number']}\n"
            f"Model: {selected_product['Model']}\n"
            f"Storage: {selected_product['Storage']}\n"
            f"Purchase Price: {selected_product['Purchase Price']}\n"
            f"Purchase Date: {selected_product['Purchase Date']}\n"
            f"Sell Price: {selected_product['Sell Price']}\n"
            f"Sell Date: {selected_product['Sell Date']}\n"
        )
    except Exception as e:
        update.message.reply_text(f"Error: {e}")
    
    return ConversationHandler.END

# Define conversation handler with states
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CHOOSE_ACTION: [MessageHandler(Filters.text & ~Filters.command, choose_action)],
        ADD_BUY: [MessageHandler(Filters.text & ~Filters.command, add_buy_entry)],
        CHOOSE_PRODUCT: [MessageHandler(Filters.text & ~Filters.command, choose_product)],
        SELL_DETAILS: [MessageHandler(Filters.text & ~Filters.command, add_sell_entry)]
    },
    fallbacks=[]
)

# Initialize Telegram Bot
def main():
    updater = Updater(os.getenv('TELEGRAM_BOT_TOKEN'), use_context=True)
    dp = updater.dispatcher

    dp.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()

# Flask route to run Telegram bot
@app.route('/')
def index():
    main()
    return 'Bot is running'

if name == '__main__':
    app.run(debug=True)
