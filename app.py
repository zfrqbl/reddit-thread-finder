import streamlit as st
import requests
import csv
import io
from datetime import datetime, timezone

st.set_page_config(page_title="Reddit Thread Finder", page_icon="🔍", layout="wide")

st.title("🔍 Reddit Topic Thread Finder & Exporter")
st.markdown("Search intersecting Reddit discussions and export the results to CSV. *(Powered by free, no-auth Reddit search).*")

# --- Sidebar for Inputs ---
with st.sidebar:
    st.header("Search Parameters")
    main_topic = st.text_input("Main Topic *", placeholder="e.g., Machine Learning")
    
    st.subheader("Advanced Options")
    sec_topic1 = st.text_input("Secondary Topic 1 (Optional)", placeholder="e.g., Ethics")
    sec_topic2 = st.text_input("Secondary Topic 2 (Optional)", placeholder="e.g., Jobs")
    sec_topic3 = st.text_input("Secondary Topic 3 (Optional)", placeholder="e.g., Open Source")
    
    target_subreddit = st.text_input("Restrict to Subreddit (Optional)", placeholder="e.g., MachineLearning")
    include_nsfw = st.checkbox("Include NSFW results", value=False, help="Keep this off to ensure safe-for-work results.")
    
    sort_by = st.selectbox("Sort By", ["score", "num_comments", "created_utc"], index=0)
    limit = st.slider("Max Results", min_value=5, max_value=50, value=10, step=5)
    
    search_btn = st.button("🔍 Search & Generate CSV", type="primary", use_container_width=True)

# --- Main Search Logic ---
if search_btn or 'search_results' in st.session_state:
    if not main_topic or not main_topic.strip():
        st.warning("⚠️ Please enter at least a main topic.")
    else:
        with st.spinner("Searching Reddit..."):
            # Build boolean query
            q = f'"{main_topic.strip()}"'
            secondary_topics = [t.strip() for t in [sec_topic1, sec_topic2, sec_topic3] if t and t.strip()]
            if secondary_topics:
                parts = [f'"{t}"' for t in secondary_topics]
                q += f' AND ({" OR ".join(parts)})'
            
            # PullPush API Endpoint (No auth required)
            url = "https://api.pullpush.io/reddit/search/submission/"
            
            params = {
                "q": q,
                "size": limit,
                "sort": sort_by,
                "order": "desc"
            }
            
            if target_subreddit and target_subreddit.strip():
                params["subreddit"] = target_subreddit.strip().replace('r/', '')
            
            try:
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                # PullPush returns data in a "data" key
                posts = data.get("data", [])
                
                # Safeguard: Filter NSFW if the user didn't explicitly opt-in
                if not include_nsfw:
                    posts = [p for p in posts if not p.get("over_18", False)]
                
                if not posts:
                    st.info("🔍 No results found. Try broadening your topics or removing secondary filters.")
                    st.stop()
                
                markdown_results = []
                csv_rows = []
                
                for post in posts:
                    created_date = datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc).strftime('%Y-%m-%d')
                    permalink = f"https://www.reddit.com{post.get('permalink', '')}"
                    post_url = post.get("url", permalink)
                    
                    md_post = f"### [{post.get('title', 'No Title')}]({post_url})\n"
                    md_post += f"- **r/{post.get('subreddit', 'unknown')}** | ⬆️ {post.get('score', 0)} | 💬 {post.get('num_comments', 0)} | 📅 {created_date}\n"
                    md_post += f"- [View on Reddit]({permalink})\n"
                    md_post += "---"
                    markdown_results.append(md_post)
                    
                    csv_rows.append({
                        "Title": post.get("title", ""),
                        "Subreddit": f"r/{post.get('subreddit', '')}",
                        "Score": post.get("score", 0),
                        "Total Comments": post.get("num_comments", 0),
                        "Date": created_date,
                        "URL": permalink,
                        "Selftext": post.get("selftext", "")[:500] if post.get("selftext") else ""
                    })
                
                st.session_state['search_results'] = "\n\n".join(markdown_results)
                st.session_state['csv_data'] = csv_rows
                
            except Exception as e:
                st.error(f"❌ Error fetching data: {str(e)}.")
                st.stop()

# --- Display Results ---
if 'search_results' in st.session_state:
    st.markdown("### 📊 Results Preview")
    st.markdown(st.session_state['search_results'])
    
    st.markdown("---")
    st.markdown("### 📥 Download Data")
    
    if 'csv_data' in st.session_state:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=st.session_state['csv_data'][0].keys())
        writer.writeheader()
        writer.writerows(st.session_state['csv_data'])
        
        st.download_button(
            label="⬇️ Download CSV",
            data=output.getvalue(),
            file_name="reddit_search_results.csv",
            mime="text/csv",
            use_container_width=True
        )
