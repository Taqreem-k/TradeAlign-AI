from app.agents.alpha_curator_agent import CuratorOutput
import datetime

class PremarketEmailAgent:
    @staticmethod
    def generate_html(curated_data: CuratorOutput) -> str:
        today = datetime.datetime.now().strftime("%B %d, %Y")

        html = f"""
        <!DOCTYPE html>
        <html>
            <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        
                <div style="border-bottom: 2px solid #2c3e50; padding-bottom: 10px; margin-bottom: 20px;">
                    <h2 style="color: #2c3e50; margin: 0;">Alpha Radar</h2>
                    <p style="color: #7f8c8d; margin: 5px 0 0 0; font-size: 14px;">Pre-Market Brief | {today}</p>
                </div>

                <div style="background-color: #e8f4f8; border-left: 4px solid #3498db; padding: 15px; margin-bottom: 30px; border-radius: 4px;">
                    <p style="margin: 0; font-size: 15px; line-height: 1.5;">
                        <em>{curated_data.introduction}</em>
                    </p>
                </div>

                <h3 style="color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px;">Top Ranked Market Movers</h3>
        """

        for index, item in enumerate(curated_data.ranked_items, 1):
            html += f"""
                <div style="margin-bottom: 25px; padding: 15px; border: 1px solid #e1e8ed; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                    <h4 style="margin: 0 0 10px 0; color: #2980b9; font-size: 16px;">
                        #{index} — Relevance Score: <span style="background: #27ae60; color: white; padding: 2px 6px; border-radius: 3px;">{item.relevance_score}/10</span>
                    </h4>
                    
                    <p style="margin: 0 0 5px 0; font-size: 12px; color: #7f8c8d; text-transform: uppercase;">Curator Reasoning</p>
                    <p style="margin: 0; font-size: 14px; line-height: 1.5; color: #2c3e50;">{item.curator_reasoning}</p>
                    
                    <div style="margin-top: 15px; font-size: 12px; color: #95a5a6;">
                        <em>Reference Digest ID: {item.digest_id}</em>
                    </div>
                </div>
            """

            html += """
                    <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center;">
                        <p style="font-size: 11px; color: #95a5a6; margin: 0;">
                            Generated autonomously by the Financial Alpha Radar pipeline.<br>
                            Do not reply to this email.
                        </p>
                    </div>
                </body>
            </html>
            """
            return html