import streamlit as st
import streamlit.components.v1 as components
import requests
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Reddit Thread Finder", page_icon="🔍", layout="wide")

# ============================================================
# HEADER
# ============================================================
st.title("🔍 Reddit Topic Thread Finder & Exporter")
st.markdown(
    "Search Reddit discussions and export the results to CSV, JSON, or Markdown. "
    
)

# ============================================================
# SIDEBAR — INPUTS
# ============================================================
with st.sidebar:
    st.header("Search Parameters")
    main_topic = st.text_input("Main Topic *", placeholder="e.g., Machine Learning")

    st.subheader("Secondary Topics")
    sec_topic1 = st.text_input("Secondary Topic 1 (Optional)", placeholder="e.g., Ethics")
    sec_topic2 = st.text_input("Secondary Topic 2 (Optional)", placeholder="e.g., Jobs")
    sec_topic3 = st.text_input("Secondary Topic 3 (Optional)", placeholder="e.g., Open Source")

    st.subheader("Scope")
    target_subreddit = st.text_input("Restrict to Subreddit (Optional)", placeholder="e.g., MachineLearning")
    include_nsfw = st.checkbox("Include NSFW results", value=False, help="Keep this off to ensure safe-for-work results.")

    # --- Improvement #2: Quality Filters ---
    st.subheader("Quality Filters")
    min_score = st.slider("Minimum Score", min_value=0, max_value=10000, value=0, step=10,
                          help="Only show posts with at least this many upvotes.")
    min_comments = st.slider("Minimum Comments", min_value=0, max_value=500, value=0, step=5,
                             help="Only show posts with at least this many comments.")

    st.subheader("Sorting & Limits")
    sort_by = st.selectbox("Sort By", ["score", "num_comments", "created_utc"], index=0)
    limit = st.slider("Max Results", min_value=5, max_value=100, value=25, step=5)

    search_btn = st.button("🔍 Search & Generate Exports", type="primary", use_container_width=True)

# ============================================================
# HELPER: Copy-to-Clipboard Component (Improvement #4)
# ============================================================
def copy_to_clipboard_button(text: str, button_label: str = "📋 Copy to Clipboard"):
    """Injects a small JS button that copies `text` to the user's clipboard."""
    # Escape quotes/backslashes for safe JS embedding
    safe_text = json.dumps(text)
    html = f"""
    <button onclick="
        navigator.clipboard.writeText({safe_text}).then(() => {{
            this.innerText = '✅ Copied!';
            setTimeout(() => {{ this.innerText = '{button_label}'; }}, 1500);
        }});
        "
        style="
            background-color: #0e1117;
            color: #fafafa;
            border: 1px solid #4a4f5a;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.95rem;
            width: 100%;
        ">
        {button_label}
    </button>
    """
    components.html(html, height=50)

# ============================================================
# HELPER: Simple Stopwords for Word Frequency (Improvement #9)
# ============================================================
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in", "on",
    "for", "with", "as", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "can", "this", "that", "these", "those", "i", "you", "he", "she",
    "it", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his",
    "its", "our", "their", "not", "no", "so", "just", "very", "too", "also",
    "any", "some", "all", "each", "every", "more", "most", "other", "than",
    "because", "about", "into", "through", "during", "before", "after", "above",
    "below", "up", "down", "out", "off", "over", "under", "again", "further",
    "https", "http", "www", "com", "reddit", "like", "know", "think", "really",
}

def tokenize(text: str) -> list:
    """Lowercase, strip punctuation, split into words."""
    text = text.lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text, flags=re.MULTILINE)
    words = re.findall(r"\b[a-z]{3,}\b", text)
    return [w for w in words if w not in STOPWORDS]

# ============================================================
# MAIN SEARCH LOGIC
# ============================================================
if search_btn or "search_results" in st.session_state:
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

            url = "https://api.pullpush.io/reddit/search/submission/"
            params = {
                "q": q,
                "size": limit,
                "sort": sort_by,
                "order": "desc",
            }
            if target_subreddit and target_subreddit.strip():
                params["subreddit"] = target_subreddit.strip().replace("r/", "")

            try:
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                posts = data.get("data", [])

                # NSFW filter
                if not include_nsfw:
                    posts = [p for p in posts if not p.get("over_18", False)]

                # --- Improvement #2: Apply quality filters client-side ---
                posts = [p for p in posts if p.get("score", 0) >= min_score]
                posts = [p for p in posts if p.get("num_comments", 0) >= min_comments]

                if not posts:
                    st.info("🔍 No results found. Try broadening your topics, removing secondary filters, or lowering the quality thresholds.")
                    st.stop()

                # Build markdown + CSV rows
                markdown_results = []
                csv_rows = []
                json_rows = []
                all_text = []  # for word frequency

                for post in posts:
                    created_date = datetime.fromtimestamp(
                        post.get("created_utc", 0), tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    permalink = f"https://www.reddit.com{post.get('permalink', '')}"
                    post_url = post.get("url", permalink)
                    title = post.get("title", "No Title")
                    subreddit = post.get("subreddit", "unknown")
                    score = post.get("score", 0)
                    num_comments = post.get("num_comments", 0)
                    selftext = post.get("selftext", "") or ""

                    md_post = (
                        f"### [{title}]({post_url})\n"
                        f"- **r/{subreddit}** | ⬆️ {score} | 💬 {num_comments} | 📅 {created_date}\n"
                        f"- [View on Reddit]({permalink})\n"
                        f"---"
                    )
                    markdown_results.append(md_post)

                    row = {
                        "Title": title,
                        "Subreddit": f"r/{subreddit}",
                        "Score": score,
                        "Total Comments": num_comments,
                        "Date": created_date,
                        "URL": permalink,
                        "Selftext": selftext[:500],
                    }
                    csv_rows.append(row)
                    json_rows.append({**row, "permalink": permalink, "post_url": post_url})

                    # Collect text for word frequency
                    all_text.append(title)
                    if selftext:
                        all_text.append(selftext)

                # Save everything to session state
                st.session_state["search_results"] = "\n\n".join(markdown_results)
                st.session_state["csv_data"] = csv_rows
                st.session_state["json_data"] = json_rows
                st.session_state["raw_posts"] = posts
                st.session_state["all_text"] = " ".join(all_text)

            except Exception as e:
                st.error(f"❌ Error fetching data: {str(e)}.")
                st.stop()

# ============================================================
# DISPLAY RESULTS
# ============================================================
if "search_results" in st.session_state:
    posts = st.session_state["raw_posts"]

    # --- Improvement #8: Stats Dashboard ---
    st.markdown("### 📊 Dashboard")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Posts", len(posts))
    with col2:
        avg_score = sum(p.get("score", 0) for p in posts) / len(posts) if posts else 0
        st.metric("Avg Score", f"{avg_score:.0f}")
    with col3:
        subreddit_counts = Counter(p.get("subreddit", "unknown") for p in posts)
        top_sub = subreddit_counts.most_common(1)[0][0] if subreddit_counts else "—"
        st.metric("Top Subreddit", f"r/{top_sub}")
    with col4:
        dates = sorted(p.get("created_utc", 0) for p in posts if p.get("created_utc"))
        if len(dates) >= 2:
            earliest = datetime.fromtimestamp(dates[0], tz=timezone.utc).strftime("%Y-%m-%d")
            latest = datetime.fromtimestamp(dates[-1], tz=timezone.utc).strftime("%Y-%m-%d")
            st.metric("Date Range", f"{earliest} → {latest}")
        else:
            st.metric("Date Range", "—")

    st.markdown("---")

    # --- Improvement #9: Word Frequency Chart ---
    st.markdown("### 🗣️ Most Common Words")
    words = tokenize(st.session_state.get("all_text", ""))
    if words:
        top_words = Counter(words).most_common(15)
        word_df = {
            "Word": [w for w, _ in top_words],
            "Count": [c for _, c in top_words],
        }
        st.bar_chart(word_df, x="Word", y="Count", horizontal=True, use_container_width=True)
    else:
        st.info("Not enough text to generate a word frequency chart.")

    st.markdown("---")

    # --- Results Preview ---
    st.markdown("### 📝 Results Preview")
    st.markdown(st.session_state["search_results"])

    # --- Improvement #4: Copy to Clipboard ---
    st.markdown("---")
    st.markdown("### 📋 Quick Actions")
    copy_to_clipboard_button(st.session_state["search_results"])

    st.markdown("---")

    # --- Downloads ---
    st.markdown("### 📥 Download Data")
    dl_col1, dl_col2, dl_col3 = st.columns(3)

    with dl_col1:
        csv_output = io.StringIO()
        writer = csv.DictWriter(csv_output, fieldnames=st.session_state["csv_data"][0].keys())
        writer.writeheader()
        writer.writerows(st.session_state["csv_data"])
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_output.getvalue(),
            file_name="reddit_search_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with dl_col2:
        st.download_button(
            label="⬇️ Download JSON",
            data=json.dumps(st.session_state["json_data"], indent=2),
            file_name="reddit_search_results.json",
            mime="application/json",
            use_container_width=True,
        )

    with dl_col3:
        st.download_button(
            label="⬇️ Download Markdown",
            data=st.session_state["search_results"],
            file_name="reddit_search_results.md",
            mime="text/markdown",
            use_container_width=True,
        )

# ============================================================
# Attribution Footer with Full Component Credits
# ============================================================
st.markdown("---")
st.markdown(
    """
    <div style="
        text-align: center; 
        color: #888; 
        font-size: 0.85rem; 
        padding: 1.5rem 0;
        border-top: 1px solid #2a2e35;
        margin-top: 2rem;
    ">
        <div style="margin-bottom: 0.5rem;">
            <strong>Built with ❤️ by Zafar Iqbal</strong>
            (<a href="https://github.com/zfrqbl" target="_blank" style="color: #ff4b4b;">@zfrqbl</a>)
        </div>
        <div style="margin-bottom: 0.5rem;">
            🛠️ Built with <a href="https://streamlit.io" target="_blank" style="color: #ff4b4b;">Streamlit</a>
            &nbsp;•&nbsp;
            🐍 Powered by <a href="https://python.org" target="_blank" style="color: #ff4b4b;">Python</a>
            &nbsp;•&nbsp;
            🔌 HTTP via <a href="https://requests.readthedocs.io" target="_blank" style="color: #ff4b4b;">requests</a>
        </div>
        <div>
            📊 Data sourced from <a href="https://pullpush.io" target="_blank" style="color: #ff4b4b;">PullPush API</a>
            &nbsp;•&nbsp;
            🌐 Hosted on <a href="https://share.streamlit.io" target="_blank" style="color: #ff4b4b;">Streamlit Community Cloud</a>
        </div>
        <div style="margin-top: 0.75rem; font-size: 0.75rem; color: #666;">
            Open source & FOSS • No data stored • Privacy-first
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
