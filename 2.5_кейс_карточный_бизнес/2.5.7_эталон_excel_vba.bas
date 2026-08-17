Attribute VB_Name = "AktivaciyaKart"
' Активация карт: чистка выгрузки и сводная по каналам.
'
' Эталонный макрос для Excel. Открыть редактор макросов (Alt+F11),
' вставить модуль, скопировать код целиком, запустить ProcessIssuedCards.
'
' Лист «Выгрузка» — исходная таблица с заголовками в первой строке.
' Результат: очищенный лист «Выгрузка» со столбцом активации,
' лист «Активация» со сводными таблицами и столбчатой диаграммой.

Option Explicit

' Номера столбцов исходной выгрузки (нумерация с единицы).
Private Const COL_ID As Long = 1
Private Const COL_ISSUED As Long = 2
Private Const COL_CHANNEL As Long = 3
Private Const COL_TARIFF As Long = 4
Private Const COL_LIMIT As Long = 6
Private Const COL_PURCHASE As Long = 7
Private Const COL_TURN30 As Long = 8
Private Const COL_TURN90 As Long = 9
Private Const COL_COUNT As Long = 10

Public Sub ProcessIssuedCards()
    Dim wsRaw As Worksheet, wsSum As Worksheet
    Dim data As Variant, clean() As Variant
    Dim seen As Object, i As Long, j As Long, n As Long
    Dim key As String, issued As Variant, purchase As Variant

    Set wsRaw = ThisWorkbook.Worksheets("Выгрузка")
    Set seen = CreateObject("Scripting.Dictionary")

    ' Читаем всё одним обращением: работа по ячейкам на таких объёмах слишком медленная.
    data = wsRaw.Range("A1").CurrentRegion.Value
    ReDim clean(1 To UBound(data, 1), 1 To COL_COUNT + 1)

    n = 0
    For i = 2 To UBound(data, 1)
        If Len(Trim$(CStr(data(i, COL_ID)))) > 0 Then
            ' Ключ повтора считаем по исходным значениям — до преобразований.
            key = ""
            For j = 1 To COL_COUNT
                key = key & CStr(data(i, j)) & "|"
            Next j

            If Not seen.Exists(key) Then
                seen.Add key, True
                n = n + 1
                For j = 1 To COL_COUNT
                    clean(n, j) = data(i, j)
                Next j
                issued = ParseDate(data(i, COL_ISSUED))
                purchase = ParseDate(data(i, COL_PURCHASE))
                clean(n, COL_ISSUED) = issued
                clean(n, COL_PURCHASE) = purchase
                clean(n, COL_CHANNEL) = NormalizeChannel(data(i, COL_CHANNEL))
                clean(n, COL_LIMIT) = ParseAmount(data(i, COL_LIMIT))
                clean(n, COL_TURN30) = ParseAmount(data(i, COL_TURN30))
                clean(n, COL_TURN90) = ParseAmount(data(i, COL_TURN90))
                clean(n, COL_COUNT + 1) = ActivationFlag(issued, purchase)
            End If
        End If
    Next i

    ' Возвращаем очищенные данные на лист.
    Application.ScreenUpdating = False
    wsRaw.Cells.ClearContents
    For j = 1 To COL_COUNT
        wsRaw.Cells(1, j).Value = data(1, j)
    Next j
    wsRaw.Cells(1, COL_COUNT + 1).Value = "Активация за 30 дней"
    wsRaw.Range(wsRaw.Cells(2, 1), wsRaw.Cells(n + 1, COL_COUNT + 1)).Value = clean
    wsRaw.Columns(COL_ISSUED).NumberFormat = "dd.mm.yyyy"
    wsRaw.Columns(COL_PURCHASE).NumberFormat = "dd.mm.yyyy"

    ' Сводные таблицы и диаграмма.
    On Error Resume Next
    Application.DisplayAlerts = False
    ThisWorkbook.Worksheets("Активация").Delete
    Application.DisplayAlerts = True
    On Error GoTo 0
    Set wsSum = ThisWorkbook.Worksheets.Add(After:=wsRaw)
    wsSum.Name = "Активация"

    Dim rowsChannels As Long, rowsTariffs As Long
    rowsChannels = WriteSummary(wsSum, clean, n, COL_CHANNEL, 1, "Канал оформления")
    rowsTariffs = WriteSummary(wsSum, clean, n, COL_TARIFF, rowsChannels + 3, "Тарифный план")

    AddChart wsSum, rowsChannels
    Application.ScreenUpdating = True

    MsgBox "Готово. Строк после чистки: " & n, vbInformation
End Sub

' Сводная по одному признаку. Возвращает номер последней занятой строки.
Private Function WriteSummary(ws As Worksheet, clean As Variant, n As Long, _
                              col As Long, startRow As Long, title As String) As Long
    Dim total As Object, active As Object, keys As Variant
    Dim i As Long, r As Long, key As String
    Set total = CreateObject("Scripting.Dictionary")
    Set active = CreateObject("Scripting.Dictionary")

    For i = 1 To n
        key = CStr(clean(i, col))
        If Not total.Exists(key) Then
            total.Add key, 0
            active.Add key, 0
        End If
        total(key) = total(key) + 1
        active(key) = active(key) + clean(i, COL_COUNT + 1)
    Next i

    ws.Cells(startRow, 1).Value = title
    ws.Cells(startRow, 2).Value = "Карт"
    ws.Cells(startRow, 3).Value = "Активировано"
    ws.Cells(startRow, 4).Value = "Доля активации, %"
    ws.Range(ws.Cells(startRow, 1), ws.Cells(startRow, 4)).Font.Bold = True

    keys = total.keys
    SortKeysByShare keys, total, active

    r = startRow
    For i = LBound(keys) To UBound(keys)
        r = r + 1
        ws.Cells(r, 1).Value = keys(i)
        ws.Cells(r, 2).Value = total(keys(i))
        ws.Cells(r, 3).Value = active(keys(i))
        ws.Cells(r, 4).Value = Round(100 * active(keys(i)) / total(keys(i)), 1)
    Next i
    WriteSummary = r
End Function

' Сортировка по доле активации по убыванию — простым перебором, объёмы небольшие.
Private Sub SortKeysByShare(keys As Variant, total As Object, active As Object)
    Dim i As Long, j As Long, tmp As Variant
    For i = LBound(keys) To UBound(keys) - 1
        For j = i + 1 To UBound(keys)
            If (active(keys(j)) / total(keys(j))) > (active(keys(i)) / total(keys(i))) Then
                tmp = keys(i): keys(i) = keys(j): keys(j) = tmp
            End If
        Next j
    Next i
End Sub

Private Sub AddChart(ws As Worksheet, lastChannelRow As Long)
    Dim ch As ChartObject
    Set ch = ws.ChartObjects.Add(Left:=360, Top:=20, Width:=420, Height:=260)
    With ch.Chart
        .ChartType = xlColumnClustered
        Do While .SeriesCollection.Count > 0
            .SeriesCollection(1).Delete
        Loop
        .SeriesCollection.NewSeries
        .SeriesCollection(1).Values = ws.Range(ws.Cells(2, 4), ws.Cells(lastChannelRow, 4))
        .SeriesCollection(1).XValues = ws.Range(ws.Cells(2, 1), ws.Cells(lastChannelRow, 1))
        .HasTitle = True
        .ChartTitle.Text = "Доля активации по каналам оформления, %"
        .HasLegend = False
    End With
End Sub

' «ОТДЕЛЕНИЕ », «Офис банка» и подобное — к одному из четырёх значений.
Private Function NormalizeChannel(value As Variant) As String
    Dim t As String
    t = LCase$(Trim$(CStr(value)))
    t = Replace(t, ChrW(1105), ChrW(1077))     ' ё → е
    If InStr(t, "отделение") = 1 Or InStr(t, "офис банка") = 1 Then
        NormalizeChannel = "Отделение"
    ElseIf InStr(t, "мобильное приложение") = 1 Or InStr(t, "мобильный банк") = 1 Or t = "мп" Then
        NormalizeChannel = "Мобильное приложение"
    ElseIf InStr(t, "сайт банка") = 1 Or InStr(t, "веб-сайт") = 1 Then
        NormalizeChannel = "Сайт банка"
    ElseIf InStr(t, "партнерская сеть") = 1 Or InStr(t, "партнер") = 1 Then
        NormalizeChannel = "Партнёрская сеть"
    Else
        NormalizeChannel = "Прочее"
    End If
End Function

' Понимает 15.03.2025 и 2025-03-15; пустое и «н/д» дают пустое значение.
Private Function ParseDate(value As Variant) As Variant
    Dim t As String
    If VarType(value) = vbDate Then
        ParseDate = CDate(value)
        Exit Function
    End If
    t = Trim$(CStr(value))
    If Len(t) = 0 Or LCase$(t) = "н/д" Then
        ParseDate = Empty
    ElseIf t Like "##.##.####" Then
        ParseDate = DateSerial(CInt(Mid$(t, 7, 4)), CInt(Mid$(t, 4, 2)), CInt(Left$(t, 2)))
    ElseIf t Like "####-##-##" Then
        ParseDate = DateSerial(CInt(Left$(t, 4)), CInt(Mid$(t, 6, 2)), CInt(Mid$(t, 9, 2)))
    Else
        ParseDate = Empty
    End If
End Function

' «12 000», «12000,50», «12000.5» — к числу; пустое даёт пустое значение.
Private Function ParseAmount(value As Variant) As Variant
    Dim t As String
    If VarType(value) = vbDouble Or VarType(value) = vbLong Or VarType(value) = vbInteger Then
        ParseAmount = CDbl(value)
        Exit Function
    End If
    t = Trim$(CStr(value))
    If Len(t) = 0 Or LCase$(t) = "н/д" Then
        ParseAmount = Empty
        Exit Function
    End If
    t = Replace(t, " ", "")
    t = Replace(t, ChrW(160), "")               ' неразрывный пробел
    t = Replace(t, ",", ".")
    ' Val понимает только точку и не зависит от региональных настроек —
    ' поэтому проверяем строку сами, а не через IsNumeric.
    If IsNumericText(t) Then
        ParseAmount = Val(t)
    Else
        ParseAmount = Empty
    End If
End Function

' Строка состоит только из цифр, одной точки и необязательного минуса.
Private Function IsNumericText(t As String) As Boolean
    Dim i As Long, c As String, dots As Long
    If Len(t) = 0 Then Exit Function
    For i = 1 To Len(t)
        c = Mid$(t, i, 1)
        If c = "." Then
            dots = dots + 1
            If dots > 1 Then Exit Function
        ElseIf c = "-" Then
            If i > 1 Then Exit Function
        ElseIf c < "0" Or c > "9" Then
            Exit Function
        End If
    Next i
    IsNumericText = True
End Function

' 1, если первая покупка была не позже 30 дней после выдачи.
Private Function ActivationFlag(issued As Variant, purchase As Variant) As Long
    Dim days As Long
    If IsEmpty(issued) Or IsEmpty(purchase) Then
        ActivationFlag = 0
        Exit Function
    End If
    days = DateDiff("d", CDate(issued), CDate(purchase))
    If days >= 0 And days <= 30 Then ActivationFlag = 1 Else ActivationFlag = 0
End Function
