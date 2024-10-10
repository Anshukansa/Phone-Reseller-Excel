import os
import io
import logging
import pandas as pd
import dropbox
import openpyxl
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from datetime import datetime, timedelta
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_ACCESS_TOKEN')

print(TELEGRAM_BOT_TOKEN)  # For debugging purposes, ensure the correct token is being printed
# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Allowed Users (Telegram User IDs)
ALLOWED_USERS = [7932502148]  # Add allowed user IDs here

# Conversation states
CHOOSE_ACTION, ADD_BUY, ADD_SELL, CHOOSE_PRODUCT, SELL_DETAILS = range(5)

# Dropbox Client
dbx = dropbox.Dropbox(os.getenv('DROPBOX_ACCESS_TOKEN'))


# Function to download Excel from Dropbox
def download_excel():
    try:
        logger.info(f"Using Dropbox Access Token: {os.getenv('DROPBOX_ACCESS_TOKEN')}")
        _, res = dbx.files_download('/Phone Management.xlsx')
        return io.BytesIO(res.content)
    except dropbox.exceptions.HttpError as e:
        logger.error(f"HTTP Error: {e}")
    except dropbox.exceptions.ApiError as e:
        logger.error(f"API Error: {e}")
    except Exception as e:
        logger.error(f"Error: {e}")
    return None

# Function to upload the modified Excel back to Dropbox
def upload_excel(file_content):
    dbx.files_upload(file_content.getvalue(), '/Phone Management.xlsx',
                     mode=dropbox.files.WriteMode.overwrite)


# Function to check if user is allowed
def allowed_user(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.from_user.id
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("You are not allowed to use this bot.")
            return ConversationHandler.END
        return await func(update, context)

    return wrapper


# Helper function to handle date input
def parse_date_input(date_str):
    """
    Parses the date input:
    - 'T' for today's date
    - 'Y' for yesterday's date
    - 'MM-DD' to append the current year

    Returns the formatted date string (YYYY-MM-DD).
    """
    current_year = datetime.now().year
    if date_str.strip().upper() == 'T':
        return datetime.now().strftime(f"%Y-%m-%d")
    elif date_str.strip().upper() == 'Y':
        return (datetime.now() - timedelta(days=1)).strftime(f"%Y-%m-%d")
    else:
        try:
            month_day = datetime.strptime(date_str.strip(), "%m-%d")
            return month_day.replace(year=current_year).strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Use 'T', 'Y', or MM-DD.")
            
# Cancel command to exit conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation canceled. No data has been saved.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Start conversation
@allowed_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [['1: Add Buy Entry', '2: Add Sell Entry']]
    await update.message.reply_text(
        "Welcome! Choose an option by typing the number:\n1: Add Buy Entry\n2: Add Sell Entry\nType /cancel to exit at any time.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CHOOSE_ACTION


# Handle chosen action (Buy or Sell)
@allowed_user
async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    if action.startswith('1'):
        await update.message.reply_text(
            "Please provide the details in this format:\nSerial Number, Model, Storage, Purchase Price, Purchase Date")
        return ADD_BUY
    elif action.startswith('2'):
        # Fetch unsold products
        excel_file = download_excel()
        if excel_file is None:
            await update.message.reply_text("Failed to download the Excel file.")
            return ConversationHandler.END

        df = pd.read_excel(excel_file)
        unsold_products = df[df['Sell Date'].isna() & df['Sell Price'].isna()]

        if unsold_products.empty:
            await update.message.reply_text("There are no unsold products.")
            return ConversationHandler.END

        products_list = "\n".join(
            [f"{idx + 1}: {row[2]} - {row[1]}" for row in unsold_products.itertuples()])

        context.user_data['unsold_products'] = unsold_products
        await update.message.reply_text(f"Choose a product to sell by number:\n{products_list}")
        return CHOOSE_PRODUCT


#Adjusting the add_buy_entry function
@allowed_user
async def add_buy_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = update.message.text.split(',')
        if len(data) != 5:
            raise ValueError("Incorrect format. Provide 5 values separated by commas.")

        # Parse the purchase date
        purchase_date = parse_date_input(data[4].strip())

        # Download Excel
        excel_file = download_excel()
        if excel_file is None:
            await update.message.reply_text("Failed to download the Excel file.")
            return ConversationHandler.END

        df = pd.read_excel(excel_file)

        # Create a new DataFrame for the new entry
        new_entry = pd.DataFrame([{
            'Index': len(df) + 1,
            'Serial Number': data[0].strip(),
            'Model': data[1].strip(),
            'Storage': data[2].strip(),
            'Purchase Price': data[3].strip(),
            'Sell Price': None,
            'Purchase Date': purchase_date,  # Use parsed date
            'Sell Date': None
        }])

        # Concatenate the new entry with the existing DataFrame
        df = pd.concat([df, new_entry], ignore_index=True)

        # Save and upload the Excel file
        excel_output = io.BytesIO()
        df.to_excel(excel_output, index=False)
        upload_excel(excel_output)

        # Send confirmation message with full details
        await update.message.reply_text(
            f"Buy entry added successfully! Here are the details:\n\n"
            f"Serial Number: {new_entry['Serial Number'][0]}\n"
            f"Model: {new_entry['Model'][0]}\n"
            f"Storage: {new_entry['Storage'][0]}\n"
            f"Purchase Price: {new_entry['Purchase Price'][0]}\n"
            f"Purchase Date: {new_entry['Purchase Date'][0]}\n"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

    return ConversationHandler.END

# Handle product selection for sell
@allowed_user
async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        product_index = int(update.message.text)
        unsold_products = context.user_data['unsold_products']

        if product_index not in unsold_products.index:
            raise ValueError("Invalid product number.")

        context.user_data['selected_product'] = product_index
        await update.message.reply_text("Provide the Sell Date (format: MM-DD (T OR Y), Price)and Sell Price:")
        return SELL_DETAILS
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END


# Handle sell entry
@allowed_user
async def add_sell_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = update.message.text.split(',')
        if len(data) != 2:
            raise ValueError("Incorrect format. Provide 2 values separated by a comma.")

        # Expecting the date in the second part of the input
        sell_date = parse_date_input(data[0].strip())  # Adjusted to parse from data[0]
        sell_price = data[1].strip()

        # Download Excel
        excel_file = download_excel()
        if excel_file is None:
            await update.message.reply_text("Failed to download the Excel file.")
            return ConversationHandler.END

        df = pd.read_excel(excel_file)

        # Update the selected product
        product_index = context.user_data['selected_product']
        df.at[product_index, 'Sell Date'] = sell_date
        df.at[product_index, 'Sell Price'] = sell_price

        # Save and upload the Excel file
        excel_output = io.BytesIO()
        df.to_excel(excel_output, index=False)
        upload_excel(excel_output)

        selected_product = df.loc[product_index]
        await update.message.reply_text(
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
        await update.message.reply_text(f"Error: {e}")

    return ConversationHandler.END


# Conversation handler now includes the /cancel command
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
        ADD_BUY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_entry)],
        CHOOSE_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_product)],
        SELL_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sell_entry)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]  # Added /cancel as a fallback
)


# Initialize Telegram Bot
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()  # Pass the actual variable
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
