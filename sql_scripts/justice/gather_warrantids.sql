---------------------------------------------------------------------------------------------------
WITH CTE_WARRANTS AS (
						SELECT
							W.WARRANTID
						FROM
							Justice.dbo.xWrntCaseBase W WITH (NOLOCK) 
								INNER JOIN ELPaso_TX.dbo.CasesToConvert CTC WITH (NOLOCK) ON W.CaseID=CTC.CaseID
						GROUP BY 
							W.WarrantID
					UNION
						SELECT
							W.WARRANTID
						FROM
							Justice.dbo.xWrntChrg W WITH (NOLOCK) 
								INNER JOIN ELPaso_TX.dbo.ChargesToConvert CTC WITH (NOLOCK) ON W.ChargeID=CTC.ChargeID
						GROUP BY 
							W.WarrantID
					UNION
						SELECT
							W.WARRANTID
						FROM
							Justice.dbo.Wrnt W
								INNER JOIN ELPaso_TX.dbo.PartiesToConvert PTC WITH (NOLOCK) ON W.DefendantID=PTC.PartyID AND PTC.TypeOfParty<>'Victim'
						GROUP BY 
							W.WarrantID
						)

						SELECT
							S.WarrantID AS WarrantID
						INTO ELPaso_TX.dbo.WarrantsToConvert 
						FROM
							CTE_WARRANTS S
						GROUP BY 
							S.WarrantID;
---------------------------------------------------------------------------------------------------
	ALTER TABLE ElPaso_TX.DBO.WarrantsToConvert ADD CONSTRAINT WarrantID PRIMARY KEY (WarrantID);
---------------------------------------------------------------------------------------------------