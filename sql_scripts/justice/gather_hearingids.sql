--------------------------------------------------------------------------------------------------
WITH CTE_HEARINGS AS
(
		SELECT
			A.HEARINGID
		FROM
			Justice.dbo.HearingEvent A WITH (NOLOCK)
				INNER JOIN ELPaso_TX.dbo.CasesToConvert CTC WITH (NOLOCK) ON A.CaseID=CTC.CaseID
	UNION
		SELECT
			A.HEARINGID
		FROM
			Justice.dbo.HearingEvent A WITH (NOLOCK)
				INNER JOIN ELPaso_TX.dbo.ChargesToConvert CTC WITH (NOLOCK) ON A.ChargeID=CTC.ChargeID
	UNION
		SELECT
			A.HEARINGID
		FROM
			Justice.dbo.HearingEvent A WITH (NOLOCK)
				INNER JOIN ELPaso_TX.dbo.WarrantsToConvert WTC WITH (NOLOCK) ON A.WarrantID=WTC.WarrantID
)
	SELECT
		A.HearingID
	INTO ELPaso_TX.dbo.HearingsToConvert
	FROM
		CTE_HEARINGS A 
	GROUP BY 
		A.HearingID;
--------------------------------------------------------------------------------------------------
	ALTER TABLE ElPaso_TX.DBO.HearingsToConvert ADD CONSTRAINT HearingID PRIMARY KEY (HearingID);
--------------------------------------------------------------------------------------------------
