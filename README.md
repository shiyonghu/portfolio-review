This is a portfolio review tool to fetch my assets from my various brokerage and bank accounts and give me a report. The first version will be a local LLM application running on my MacBook. 

# The purpose of this tool
Our family has many investment and bank accounts. We want to know the overall asset value, the overall asset allocation between different asset types, the asset values in taxable and tax-advantaged accounts, and the asset allocation in taxable and tax-advantaged accounts. These insights can help us decide how to adjust our asset allocation. 

Every time we use the tool to generate a portfolio snapshot, we also want to store the processed data locally so we can compare in the future. 

# User Journey
## 1. Initial setup
Allow user to link all the investment and bank accounts with Plaid. Then store the credentials locally so that I don’t need to log in to all these accounts next time. 
Also allow user to configure what account to opt-out in this tool. Let’s say I have a brokerage account and a 529 account under Fidelity, I may want to opt-out the 529 account in portfolio analysis. Store this preference.

## 2. Portfolio Processing
User kick off a portfolio analysis workflow. It first fetches all active holdings (with asset name, current value) from the accounts we have in the initial setup (excluding the opted out ones). Store the raw data locally for debugging purpose. 
For each account, run an analysis to break down the asset types (see below on the categorization) and their values. Store them into a csv file with date on it. Also compute the overall total asset value, and value of each asset types in the csv file. 

### Asset types
I want the assets to be categorized in these types: 
- Cash
- Bond
- Equity
- Gold
- Commodity
- Crypto

## 3. Ask Agent
Now with all the data from step 2, user can ask LLM model any question about the portfolio like to draw a pie chart of asset allocation. Or draw a line graph for the total asset value over time. 
