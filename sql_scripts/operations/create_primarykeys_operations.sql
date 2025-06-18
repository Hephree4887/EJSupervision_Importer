-- First batch
BEGIN TRY
    DROP TABLE IF EXISTS ${DB_NAME}.dbo.PrimaryKeyScripts_Operations;
END TRY
BEGIN CATCH
    DECLARE @ErrorMessage1 NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@ErrorMessage1, 16, 1);
END CATCH
GO
    
-- Second batch
BEGIN TRY
    CREATE TABLE ${DB_NAME}.dbo.PrimaryKeyScripts_Operations
    (
         ScriptType NVARCHAR(50)-- 'PK' or 'NOT_NULL'
        ,DatabaseName SYSNAME
        ,SchemaName SYSNAME
        ,TableName SYSNAME
        ,Script NVARCHAR(MAX)
    );
END TRY
BEGIN CATCH
    DECLARE @ErrorMessage2 NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@ErrorMessage2, 16, 1);
END CATCH
GO
    
-- Third batch
BEGIN TRY
    -- Insert PK scripts
    INSERT INTO ${DB_NAME}.dbo.PrimaryKeyScripts_Operations (ScriptType,DatabaseName,SchemaName,TableName,Script)
        SELECT 'PK','${DB_NAME}',S.[NAME],T.[NAME],
            'ALTER TABLE [${DB_NAME}].[dbo].[Operations_' + t.name + '] ADD CONSTRAINT [Op_' + kc.name + '] PRIMARY KEY (' +STUFF((SELECT ', [' + c2.name + ']' FROM Operations.sys.index_columns ic2 JOIN Operations.sys.columns c2 ON c2.object_id=ic2.object_id AND c2.column_id=ic2.column_id WHERE ic2.object_id=t.object_id AND ic2.index_id=kc.unique_index_id ORDER BY ic2.key_ordinal FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') + ')' AS Script 
        FROM 
            Operations.sys.tables t
                INNER JOIN Operations.sys.schemas s ON t.schema_id=s.schema_id
                INNER JOIN Operations.sys.key_constraints kc ON kc.parent_object_id=t.object_id AND kc.type='PK';
END TRY
BEGIN CATCH
    DECLARE @ErrorMessage3 NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@ErrorMessage3, 16, 1);
END CATCH
GO

-- Fourth batch
BEGIN TRY
    -- Insert NOT NULL constraints
    INSERT INTO ${DB_NAME}.dbo.PrimaryKeyScripts_Operations (ScriptType,DatabaseName,SchemaName,TableName,Script)
        SELECT 'NOT_NULL','${DB_NAME}',S.[NAME],T.[NAME],
            'ALTER TABLE [${DB_NAME}].[dbo].[Operations_' + t.name + '] ALTER COLUMN [' + c.name + '] ' + UPPER(case tp.system_type_id when 36 then 'uniqueidentifier' when 48 then 'tinyint' when 52 then 'smallint' when 56 then 'int' when 61 then 'datetime' when 104 then 'flag' when 127 then 'bigint' when 167 then 'varchar' when 175 then 'char' else tp.[name] end) + CASE WHEN case tp.system_type_id when 36 then 'uniqueidentifier' when 48 then 'tinyint' when 52 then 'smallint' when 56 then 'int' when 61 then 'datetime' when 104 then 'flag' when 127 then 'bigint' when 167 then 'varchar' when 175 then 'char' else tp.[name] end IN ('varchar', 'char', 'varbinary', 'binary') THEN '(' + CASE WHEN c.max_length=-1 THEN 'MAX' ELSE CAST(c.max_length AS VARCHAR(10)) END + ')' WHEN case tp.system_type_id when 36 then 'uniqueidentifier' when 48 then 'tinyint' when 52 then 'smallint' when 56 then 'int' when 61 then 'datetime' when 104 then 'flag' when 127 then 'bigint' when 167 then 'varchar' when 175 then 'char' else tp.[name] end IN ('nvarchar', 'nchar') THEN '(' + CASE WHEN c.max_length=-1 THEN 'MAX' ELSE CAST(c.max_length / 2 AS VARCHAR(10)) END + ')' WHEN case tp.system_type_id when 36 then 'uniqueidentifier' when 48 then 'tinyint' when 52 then 'smallint' when 56 then 'int' when 61 then 'datetime' when 104 then 'flag' when 127 then 'bigint' when 167 then 'varchar' when 175 then 'char' else tp.[name] end IN ('decimal', 'numeric') THEN '(' + CAST(c.precision AS VARCHAR) + ',' + CAST(c.scale AS VARCHAR) + ')' ELSE '' END + ' NOT NULL' AS Script
        FROM 
            Operations.sys.tables t
                INNER JOIN Operations.sys.schemas s ON t.schema_id=s.schema_id
                INNER JOIN Operations.sys.key_constraints kc ON kc.parent_object_id=t.object_id AND kc.type='PK'
                INNER JOIN Operations.sys.index_columns ic ON ic.object_id=kc.parent_object_id AND ic.index_id=kc.unique_index_id
                INNER JOIN Operations.sys.columns c ON c.object_id=t.object_id AND c.column_id=ic.column_id
                INNER JOIN Operations.sys.types tp ON c.user_type_id=tp.user_type_id;
END TRY
BEGIN CATCH
    DECLARE @ErrorMessage4 NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@ErrorMessage4, 16, 1);
END CATCH
GO
