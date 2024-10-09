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
